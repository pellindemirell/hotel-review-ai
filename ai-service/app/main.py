import os
import re
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional

# Servisleri İçe Aktar
from app.services.translation_service import TranslationService
from app.services.sentiment_service import SentimentService
from app.services.category_service import CategoryService
from app.services.keyword_service import KeywordService
from app.services.ocr_service import OcrService
from app.services.rag_service import RagService
from app.services.scraper_service import ScraperService
from app.services.multi_scraper_service import MultiScraperService
from app.services.review_ingestion_schema import IngestedReview
from app.services.absa_service import AbsaService, split_clauses_absa
from app.services.analytics_service import AnalyticsService
from app.services.review_store import get_review_store
from app.services.room_issue_service import get_room_issue_service
from app.services.hotel_agent_service import HotelAgentService
from app.services.ops_copilot_adapter import OpsCopilotAdapter, get_ops_copilot_adapter
from app.services.hotel_knowledge_service import HotelKnowledgeService
from app.services.intent_service import IntentService
from app.services.entity_tracker_service import get_entity_tracker_service
from app.services.ontology_service import OntologyService
from app.services.learning_service import get_learning_service
from app.services.feedback_service import get_feedback_service
from app.services.collector_service import import_paste_text, get_csv_template, analyze_collected_csv, import_bulk_paste
from app.services.turkish_nlp_utils import normalize_turkish
from app.services.absa_service import split_clauses_absa
from app.review_intelligence import ReviewIntelligenceService
from app.operational_intelligence.engine import HodipEngine
from app.services.deep_llm_service import DeepHotelLLMService
from app.services.eval_service import EvalService, SystemEvaluationReport
from app.security import api_key_middleware, allowed_origins

# Loglama Yapılandırması
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_service")

app = FastAPI(
    title="Otel / Restoran Akıllı Yorum Analiz Sistemi - Yapay Zeka Servisi",
    description="Sentiment, Kategori Sınıflandırma, Anahtar Kelime Çıkarma, OCR ve RAG Servisi",
    version="1.1.0"
)

# Erişim denetimi: varsayılan kapalı, allowlist dışındaki her uç API anahtarı ister.
# NOT: Starlette middleware'leri EKLENME SIRASININ TERSİNE çalışır; CORS'un
# anahtar denetiminden önce çalışması için ondan SONRA eklenmesi gerekir, aksi
# hâlde 401/503 yanıtlarında CORS başlığı bulunmaz ve tarayıcı gövdeyi okuyamaz.
app.middleware("http")(api_key_middleware)

# CORS Middleware Ekle
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kategori Servisini Başlat
category_service = CategoryService()
review_store = get_review_store()
room_issue_service = get_room_issue_service()
entity_tracker_service = get_entity_tracker_service()
learning_service = get_learning_service()
feedback_service = get_feedback_service()
review_intelligence_service = ReviewIntelligenceService()
hodip_engine = HodipEngine()

# Adaptive timeout: UI fast-path hedef <5s. Ağır işler ayrı executor'da, terk edilen iş ana pool'u tıkamaz.
ANALYZE_TIMEOUT_SEC = float(os.getenv("ANALYZE_TIMEOUT_SEC", "120"))
ANALYZE_INCLUDE_RI_DEFAULT = os.getenv("ANALYZE_INCLUDE_RI", "0").strip().lower() in ("1", "true", "yes")
# Analiz için ayrı havuz — RI / warmup ile paylaşılmaz; terk edilen işler diğer istekleri bloke etmesin
_ANALYZE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="review-analyze")
_SIDE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="review-side")
_RI_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="review-ri")
_analyze_generation = 0
_analyze_gen_lock = threading.Lock()

# --- İstek / Cevap Şemaları ---

class ReviewRequest(BaseModel):
    comment: str = Field(..., description="Müşteri yorumu")
    rating: Optional[int] = Field(None, description="Yorum puanı (1-5)")
    language: Optional[str] = Field(None, description="Yorum dili (Opsiyonel)")
    api_key: Optional[str] = Field(None, description="Gemini API Anahtarı (Opsiyonel, mükemmel doğruluk için)")
    includeReviewIntelligence: Optional[bool] = Field(
        None,
        description="True ise Review Intelligence senkron çalışır (yavaş). Varsayılan: kapalı (hızlı UI yolu).",
    )
    hodip_mode: Optional[str] = Field(
        None,
        description="HODIP modu: 'off' | 'light' (sadece özet) | 'full' (tüm zincir). Varsayılan: off.",
    )

class ReviewResponse(BaseModel):
    sentiment: str
    sentimentScore: float
    category: str
    keywords: List[str]
    summary: str
    suggestion: str
    confidence: float
    predictedRating: Optional[int] = Field(None, description="Kullanıcı puanı yoksa AI tahmini (1-5)")
    userRating: Optional[int] = Field(None, description="Kullanıcının girdiği puan (1-5)")
    classificationMethod: Optional[str] = Field(None, description="rules|model|gemini|fallback")
    isManipulation: bool = Field(False, description="Sahte yüksek puan / görünürlük manipülasyonu")
    isMixedReview: bool = Field(False, description="Karışık yorum (ama/fakat)")
    secondaryCategory: Optional[str] = Field(None, description="Karışık yorumda ikincil kategori")
    absaAspects: Optional[List[dict]] = Field(None, description="ABSA çoklu aspect sonuçları")
    absaDepartmentSummary: Optional[dict] = Field(None, description="ABSA birim özeti")
    reviewId: Optional[str] = Field(None, description="Depolanan yorum kimliği")
    learned: Optional[bool] = Field(None, description="Öğrenme buffer'a eklendi mi")
    reviewIntelligence: Optional[dict] = Field(None, description="DOC-004 Review Intelligence pipeline çıktısı")
    hodip: Optional[dict] = Field(None, description="HODIP v2.0 — Hotel Operational Decision Intelligence çıktısı")

class TranslateRequest(BaseModel):
    text: str = Field(..., description="Çevrilecek metin")
    sourceLang: Optional[str] = Field(None, description="Bilinen kaynak dil (opsiyonel ipucu)")


class TranslateResponse(BaseModel):
    translatedText: str
    detectedLang: str
    alreadyTurkish: bool


class BatchReviewRequest(BaseModel):
    comments: List[ReviewRequest]

class BatchReviewResponse(BaseModel):
    analysis_results: List[ReviewResponse]

class AbsaAspectResponse(BaseModel):
    clause: str
    aspect: str
    department: str
    sentiment: str
    sentimentScore: float
    confidence: float
    priority: str
    priorityScore: int
    satisfactionLevel: str
    keywords: List[str]
    suggestion: str
    llmExplanation: Optional[str] = None
    llmStatus: Optional[str] = None

class AbsaResponse(BaseModel):
    aspects: List[AbsaAspectResponse]
    overallSentiment: str
    overallScore: float
    isMultiAspect: bool
    aspectCount: int
    departmentSummary: dict
    operationalSummary: str = ""

class MultiDomainAbsaAspectResponse(BaseModel):
    clause: str
    domain: str
    domainLabel: str
    department: str
    departmentLabel: str
    aspect: str
    aspectLabel: str
    sentiment: str
    sentimentScore: float
    confidence: float
    priority: str
    priorityScore: int
    satisfactionLevel: str
    keywords: List[str]
    suggestion: str

class MultiDomainAbsaResponse(BaseModel):
    aspects: List[MultiDomainAbsaAspectResponse]
    overallSentiment: str
    overallScore: float
    isMultiAspect: bool
    aspectCount: int
    domainSummary: dict
    departmentSummary: dict
    operationalSummary: str = ""

class MultiDomainReviewRequest(BaseModel):
    comment: str = Field(..., description="Müşteri yorumu")
    rating: Optional[int] = Field(None, description="Yorum puanı (1-5)")
    language: Optional[str] = Field(None, description="Yorum dili")
    domainHint: Optional[str] = Field(None, description="Alan ipucu (hotel, bank, ...)")

class OcrResponse(BaseModel):
    ocr_text: str
    quality_score: float

class ChatRequest(BaseModel):
    query: str = Field(..., description="Chatbot sorusu")
    api_key: Optional[str] = Field(None, description="Gemini API Anahtarı (Opsiyonel)")
    session_id: Optional[str] = Field(None, description="Oturum kimliği — çok turlu bağlam için")
    role: Optional[str] = Field(None, description="Kullanıcı rolü: guest | manager")

class ChatResponse(BaseModel):
    response: str = Field(..., description="Chatbot cevabı")
    data_source: Optional[str] = Field(None, description="RAG veri kaynağı özeti")
    indexed_records: Optional[int] = Field(None, description="İndeksteki toplam kayıt sayısı")
    matches_found: Optional[int] = Field(None, description="Sorguya benzer bulunan kayıt sayısı")
    mode: Optional[str] = Field(None, description="local | hotel_knowledge | entity_tracker | rag | ...")
    room_number: Optional[str] = Field(None, description="Oda sorgusu tespit edildiyse oda numarası")
    room_report: Optional[dict] = Field(None, description="Oda operasyon raporu (yapılandırılmış)")
    entity_type: Optional[str] = Field(None, description="Entity sorgusu tespit edildiyse entity tipi")
    entity_id: Optional[str] = Field(None, description="Entity sorgusu tespit edildiyse entity id")
    intent: Optional[str] = Field(None, description="Tespit edilen intent")
    department: Optional[str] = Field(None, description="Yönlendirilen departman")
    priority: Optional[str] = Field(None, description="Öncelik: low|medium|high")
    action_required: Optional[bool] = Field(None, description="Aksiyon gerekli mi")
    sources: Optional[List[str]] = Field(None, description="Yanıt kaynakları")

class OpsChatRequest(BaseModel):
    query: str = Field(..., description="Personel operasyon sorusu")
    session_id: Optional[str] = Field(None, description="Oturum kimliği")
    role: Optional[str] = Field("duty_manager", description="Staff rolü")
    hotel_id: Optional[str] = Field("h1", description="Otel kimliği")

class OpsChatResponse(BaseModel):
    answer: str
    mode: str = "ops_copilot"
    plan: Optional[dict] = None
    tool_results: Optional[list] = None
    tools_used: Optional[list] = None
    request_id: Optional[str] = None
    intent: Optional[str] = None
    department: Optional[str] = None
    priority: Optional[str] = None
    action_required: Optional[bool] = None

class HotelAgentRequest(BaseModel):
    query: str = Field(..., description="Otel AI Agent sorusu")
    api_key: Optional[str] = Field(None, description="Gemini API Anahtarı (Opsiyonel)")
    session_id: Optional[str] = Field(None, description="Oturum kimliği — çok turlu bağlam için")
    role: Optional[str] = Field(None, description="Kullanıcı rolü: guest | manager")

class HotelAgentResponse(BaseModel):
    answer: str
    intent: str
    department: str
    priority: str
    action_required: bool
    sources: List[str] = Field(default_factory=list)
    mode: str
    entities: Optional[dict] = None
    matched_question: Optional[str] = None
    confidence: Optional[float] = None
    rag_meta: Optional[dict] = None

class HotelProfileUpdate(BaseModel):
    profile: dict = Field(..., description="Güncellenecek otel profili")

class CorrectedItem(BaseModel):
    comment: str = Field(..., description="Düzeltilen yorum metni")
    category: str = Field(..., description="Yöneticinin belirlediği doğru kategori")
    sentiment: Optional[str] = Field("NEGATIVE", description="Duygu durumu")

class RetrainRequest(BaseModel):
    data: List[CorrectedItem] = Field(..., description="Düzeltilmiş etiket veri listesi")

class LearnFeedbackRequest(BaseModel):
    review_id: str = Field(..., description="Düzeltilecek yorum kimliği")
    correct_category: str = Field(..., description="Doğru kategori")
    correct_sentiment: str = Field(..., description="Doğru duygu: Positive|Negative|Neutral")
    notes: Optional[str] = Field("", description="Ek notlar")

class LearnRetrainRequest(BaseModel):
    force: bool = Field(False, description="Eşik beklemeden zorla eğit")

class BulkTrainRequest(BaseModel):
    reviews_dir: Optional[str] = Field(None, description="CSV/JSON yorum dizini")
    include_long: bool = Field(True, description="Uzun yorumları cümleciklere böl")
    retrain_absa: bool = Field(True, description="Kategori modeli + RAG yeniden eğit")
    export_weights: bool = Field(False, description="Model ağırlıklarını dışa aktar")
    include_mega: bool = Field(False, description="mega_reviews CSV'den örnek ekle")
    mega_limit: int = Field(500, ge=0, le=5000)

class TrainFromCsvRequest(BaseModel):
    csv_path: str = Field(..., description="Sunucudaki CSV dosya yolu")
    include_long: bool = Field(True)
    retrain_absa: bool = Field(True)
    export_weights: bool = Field(False)

class ScrapeRequest(BaseModel):
    url: str = Field("", description="TripAdvisor, Google Maps linki veya boş (CSV modunda)")
    limit: int = Field(10, ge=1, le=50, description="Maksimum yorum sayısı")
    max_per_source: Optional[int] = Field(None, ge=1, le=100, description="Kaynak başına max yorum")
    analyze: bool = Field(True, description="Yorumları AI ile etiketle")
    allow_fallback: bool = Field(True, description="Canlı kazıma başarısızsa demo veri kullan")
    api_key: Optional[str] = Field(None, description="Gemini API anahtarı (kategori için)")
    google_places_api_key: Optional[str] = Field(None, description="Google Places API anahtarı")
    google_api_key: Optional[str] = Field(None, description="Google Places API anahtarı (alias)")
    google_place_id: Optional[str] = Field(None, description="Google Place ID (ChIJ...)")
    csv_path: Optional[str] = Field(None, description="Sunucudaki CSV dosya yolu")
    sources: Optional[List[str]] = Field(None, description="Çoklu kaynak listesi veya sources dict kullanın")
    source_urls: Optional[dict] = Field(None, description="Platform URL'leri: {booking, tripadvisor, agoda, ...}")
    hotel_name: Optional[str] = Field(None, description="Otel adı (çoklu kaynak modu)")
    city: Optional[str] = Field(None, description="Şehir")
    country: Optional[str] = Field(None, description="Ülke")
    urls: Optional[dict] = Field(None, description="Platform URL/CSV yolları (alias: source_urls)")


class PlaywrightScrapeRequest(BaseModel):
    url: str = Field(..., description="Google Maps URL")
    max_reviews: int = Field(0, description="0 = tümü")
    all_sorts: bool = Field(True, description="4 sıralamayı da tara")
    analyze: bool = Field(True, description="AI ile etiketle")
    api_key: Optional[str] = Field(None, description="Gemini API anahtarı")


class MultiScrapeRequest(BaseModel):
    hotel_name: str = Field(..., description="Otel adı")
    city: str = Field("", description="Şehir")
    country: str = Field("", description="Ülke")
    sources: List[str] = Field(default=["google"], description="Kaynak listesi")
    urls: Optional[dict] = Field(None, description="Platform URL/CSV yolları")
    limit: int = Field(10, ge=1, le=100)
    analyze: bool = Field(True)
    allow_fallback: bool = Field(True)
    api_key: Optional[str] = Field(None, description="Gemini API anahtarı")
    google_places_api_key: Optional[str] = Field(None, description="Google Places API anahtarı")
    csv_path: Optional[str] = Field(None, description="CSV dosya yolu")
    column_mapping: Optional[dict] = Field(None, description="CSV sütun eşlemesi")


class IngestedReviewAnalysis(BaseModel):
    department: str = ""
    aspect: str = ""
    sentiment: str = "Neutral"
    urgency: str = "low"
    need_action: bool = False
    suggested_response: str = ""
    action_item: str = ""
    absa_aspects: Optional[List[dict]] = None
    sentiment_score: float = 0.0
    category: str = ""
    confidence: float = 0.0
    keywords: Optional[List[str]] = None
    summary: str = ""
    satisfaction_level: str = ""
    translated_comment: str = ""
    detected_language: str = ""


class IngestedReviewItem(BaseModel):
    hotel: str = ""
    country: str = ""
    city: str = ""
    language: str = ""
    platform: str = ""
    date: str = ""
    rating: float = 0.0
    title: str = ""
    comment: str = ""
    traveler_type: str = ""
    room_type: str = ""
    stay_duration: str = ""
    trip_purpose: str = ""
    positive_text: str = ""
    negative_text: str = ""
    guest_name: str = "Anonim"
    helpful_count: int = 0
    is_most_helpful: bool = False
    comment_hash: str = ""
    analysis: Optional[IngestedReviewAnalysis] = None


class MultiScrapeResponse(BaseModel):
    reviews: List[IngestedReviewItem]
    total: int
    raw_total: int = 0
    duplicates_removed: int = 0
    sources_requested: List[str] = []
    sources_succeeded: List[str] = []
    source_stats: Optional[dict] = None
    methods: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []
    legal_notices: List[str] = []
    hotel: str = ""
    city: str = ""
    country: str = ""

class ScrapedReviewAnalysis(BaseModel):
    sentiment: str
    sentimentScore: float
    category: str
    keywords: List[str]
    summary: str
    suggestion: str
    confidence: float

class ScrapedReviewItem(BaseModel):
    guest_name: str
    comment: str
    rating: Optional[int] = None
    source: str
    review_date: Optional[str] = None
    platform: Optional[str] = None
    language: Optional[str] = None
    helpful_count: int = 0
    is_most_helpful: bool = False
    badge_color: Optional[str] = None
    badge_label: Optional[str] = None
    title: Optional[str] = None
    analysis: Optional[ScrapedReviewAnalysis] = None

class ScrapeResponse(BaseModel):
    reviews: List[ScrapedReviewItem]
    total: int
    method: str
    source_detected: str
    warning: Optional[str] = None
    source_stats: Optional[dict] = None
    sources_succeeded: Optional[List[str]] = None


class CollectorPasteRequest(BaseModel):
    text: str = Field(..., min_length=3, description="Yapıştırılmış yorum blokları")
    hotel_name: str = "Hotel"
    country: str = "Turkey"
    city: str = "Antalya"
    platform: str = "manual"
    analyze: bool = True
    limit: int = Field(default=50, ge=1, le=100)
    api_key: Optional[str] = None


class CollectorPasteResponse(BaseModel):
    success: bool
    count: int = 0
    skipped_dup: int = 0
    path: str = ""
    preview: List[dict] = Field(default_factory=list)
    analysis_total: Optional[int] = None
    analysis_reviews: Optional[List[dict]] = None
    format_detected: Optional[str] = None
    error: Optional[str] = None


class CollectorBulkRequest(BaseModel):
    text: str = Field(..., min_length=3, description="Google/TripAdvisor kopyala-yapıştır yorumları")
    hotel_name: str = "Crystal Waterworld Resort & Spa"
    country: str = "TR"
    city: str = "Belek"
    analyze: bool = True
    limit: int = Field(default=50, ge=1, le=100)
    api_key: Optional[str] = None
    force: bool = True

# --- Endpointler ---

@app.get("/", response_class=HTMLResponse, summary="Görsel Kontrol Paneli (Web UI)")
def read_root():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>Web UI Yüklenemedi</h3>"

@app.post("/translate", summary="Metni Türkçeye çevir", response_model=TranslateResponse)
async def translate_text(request: TranslateRequest):
    """
    Tek bir metni Türkçeye çevirir.

    TranslationService zaten /analyze-review içinde kullanılıyordu ama dışarıya
    açılmamıştı; panelin "Türkçeye çevir" butonu bu ucu çağırıyor.
    """
    text = (request.text or "").strip()
    if not text:
        return TranslateResponse(translatedText="", detectedLang="unknown", alreadyTurkish=False)

    # Çeviri ağ I/O'su senkron; doğrudan çağrılırsa event loop'u bloke eder ve
    # /health dahil hiçbir uç yanıt veremez (analyze-review ile aynı gerekçe).
    def _run() -> tuple[str, str]:
        return TranslationService.translate_to_turkish(text=text, source_lang=request.sourceLang)

    translated, detected = await asyncio.get_running_loop().run_in_executor(
        _ANALYZE_EXECUTOR, _run
    )

    return TranslateResponse(
        translatedText=translated,
        detectedLang=detected,
        # Metin zaten Türkçeyse servis onu aynen döndürüyor; çağıran taraf
        # "çeviri gerekmedi" durumunu ayırt edebilsin.
        alreadyTurkish=(detected == "tr"),
    )


@app.get("/health", summary="Sağlık Kontrolü")
@app.get("/health-status", summary="Sağlık Kontrolü")
async def health_check():
    return {"status": "ok"}

def _should_run_absa(text: str, is_mixed: bool) -> bool:
    """Her yorumda ABSA tetiklenir — aspect coverage için."""
    return True


def _run_absa_lightweight(
    turkish_comment: str,
    rating: Optional[int],
    is_mixed: bool,
) -> Optional[dict]:
    """UI fast-path ABSA — multidomain/ontology yok, store yok."""
    if not _should_run_absa(turkish_comment, is_mixed):
        return None
    result = AbsaService.analyze(turkish_comment, rating=rating, multidomain=False)
    return AbsaService.to_dict(result)


def _side_persist(comment: str, rating: Optional[int], resp_dict: dict, absa_aspects: Optional[list]) -> None:
    """Store / entity / learning — ayrı havuzda, UI yanıtını bloke etmez."""
    try:
        stored = review_store.add_from_analysis(comment, rating, resp_dict, source="live")
        stored_id = stored.id
    except Exception:
        stored_id = None
    try:
        room_issue_service.register_from_comment(comment, review_id=stored_id, created_at=None)
        entity_tracker_service.register_from_comment(comment, review_id=stored_id, created_at=None)
    except Exception:
        logger.debug("_side_persist: hata yutuldu", exc_info=True)
    try:
        learning_service.record_from_analysis(
            review_id=stored_id or f"anon-{hash(comment) & 0xFFFFFF:06x}",
            comment=comment,
            rating=rating,
            analysis=resp_dict,
            absa_aspects=absa_aspects,
            source="live",
        )
    except Exception:
        logger.debug("_side_persist: hata yutuldu", exc_info=True)


def _analyze_review_sync(request: ReviewRequest, generation: int = 0) -> ReviewResponse:
    """UI FAST PATH: kategori + duygu + hafif ABSA + öneri. RAG/RI/store yok."""
    import time as _time
    _t0 = _time.perf_counter()
    _stage_ms: dict[str, float] = {}
    # Fast-path sert tavan — timeout'tan önce kısmi sonuç dön
    _DEADLINE = _t0 + min(ANALYZE_TIMEOUT_SEC - 1.0, 8.0)

    def _abandoned() -> bool:
        return generation > 0 and generation != _analyze_generation

    def _mark(stage: str, started: float) -> float:
        _stage_ms[stage] = (_time.perf_counter() - started) * 1000
        return _time.perf_counter()

    def _past_deadline() -> bool:
        return _time.perf_counter() > _DEADLINE or _abandoned()

    t = _time.perf_counter()
    src_lang = request.language
    if not src_lang and re.search(r"[çğıöşüÇĞİÖŞÜ]", request.comment or ""):
        src_lang = "tr"
    turkish_comment, detected_lang = TranslationService.translate_to_turkish(
        text=request.comment,
        source_lang=src_lang,
    )
    t = _mark("translation", t)
    if _abandoned():
        raise TimeoutError("abandoned")

    is_manipulation = SentimentService.is_manipulation(turkish_comment, request.rating)
    sentiment, sentiment_score = SentimentService.analyze_sentiment(
        text=turkish_comment,
        rating=request.rating,
    )
    t = _mark("sentiment", t)

    category, confidence, class_method, secondary_cat, is_mixed = category_service.classify_category(
        turkish_comment, request.api_key, use_gemini=bool(request.api_key),
    )
    t = _mark("category", t)

    keywords = KeywordService.extract_keywords(turkish_comment, max_keywords=6)
    summary = RagService.generate_summary(turkish_comment)
    suggestion = RagService.generate_suggestion(
        category=category, text=turkish_comment, keywords=keywords,
        sentiment=sentiment, is_mixed=is_mixed,
        secondary_category=secondary_cat, is_manipulation=is_manipulation,
    )
    t = _mark("keywords_summary_suggestion", t)

    predicted_rating = None
    if request.rating is None:
        predicted_rating = SentimentService.predict_rating(
            turkish_comment, sentiment, sentiment_score,
        )

    resp = ReviewResponse(
        sentiment=sentiment,
        sentimentScore=sentiment_score,
        category=category,
        keywords=keywords,
        summary=summary,
        suggestion=suggestion,
        confidence=confidence,
        predictedRating=predicted_rating,
        userRating=request.rating,
        classificationMethod=class_method,
        isManipulation=is_manipulation,
        isMixedReview=is_mixed,
        secondaryCategory=secondary_cat,
    )

    # Hafif ABSA — deadline varsa atla
    absa_data = None
    if not _past_deadline():
        try:
            t_a = _time.perf_counter()
            absa_data = _run_absa_lightweight(turkish_comment, request.rating, is_mixed)
            _mark("absa", t_a)
        except Exception as absa_err:
            logger.warning(f"ABSA atlandı: {absa_err}")
    if absa_data:
        resp.absaAspects = absa_data.get("aspects")
        resp.absaDepartmentSummary = absa_data.get("departmentSummary")

    # RI yalnızca açıkça istenirse ve deadline varsa
    include_ri = (
        request.includeReviewIntelligence
        if request.includeReviewIntelligence is not None
        else ANALYZE_INCLUDE_RI_DEFAULT
    )
    if include_ri and not _past_deadline():
        try:
            t_ri = _time.perf_counter()
            ri_result = review_intelligence_service.analyze(
                review_text=turkish_comment,
                review_id=None,
                rating=request.rating,
                metadata={"source": "analyze-review"},
                language=src_lang or detected_lang,
            )
            resp.reviewIntelligence = ri_result.to_dict()
            _mark("review_intelligence", t_ri)
        except Exception as ri_err:
            logger.debug(f"Review Intelligence atlandı: {ri_err}")

    # HODIP — isteğe bağlı
    hodip_mode = request.hodip_mode or "off"
    if hodip_mode != "off" and not _past_deadline():
        try:
            t_h = _time.perf_counter()
            hodip_result = hodip_engine.analyze(
                comment=turkish_comment,
                review_id=resp.reviewId or f"hodip-{hash(turkish_comment) & 0xFFFFFF:06x}",
                rating=request.rating,
                language=src_lang or detected_lang,
            )
            if hodip_mode == "light":
                hodip_result.pop("facts", None)
            resp.hodip = hodip_result
            _mark("hodip", t_h)
        except Exception as hodip_err:
            logger.debug(f"HODIP atlandı: {hodip_err}")

    total_ms = (_time.perf_counter() - _t0) * 1000
    slow = {k: round(v) for k, v in _stage_ms.items() if v >= 200}
    logger.info(
        f"/analyze-review ok {total_ms:.0f}ms "
        f"fast=1 ri={'on' if include_ri else 'off'} "
        f"hodip={hodip_mode} "
        f"lang={detected_lang} mixed={is_mixed}"
        + (f" SLOW={slow}" if slow else "")
    )
    return resp


@app.post("/analyze-review-legacy", response_model=ReviewResponse, summary="Tekli Yorum Analizi (legacy)")
async def analyze_review(request: ReviewRequest, background_tasks: BackgroundTasks):
    """UI fast-path: kategori+duygu+hafif ABSA+öneri. Store/RAG/entity arka planda."""
    global _analyze_generation
    with _analyze_gen_lock:
        _analyze_generation += 1
        gen = _analyze_generation
    try:
        loop = asyncio.get_running_loop()
        resp = await asyncio.wait_for(
            loop.run_in_executor(_ANALYZE_EXECUTOR, partial(_analyze_review_sync, request, gen)),
            timeout=ANALYZE_TIMEOUT_SEC,
        )
        # Yan etkiler ayrı havuzda — yanıtı ve analiz pool'unu bloke etmez
        _SIDE_EXECUTOR.submit(
            _side_persist,
            request.comment,
            request.rating,
            _analysis_to_dict(resp),
            resp.absaAspects,
        )
        return resp
    except asyncio.TimeoutError:
        # Terk edilen işleri işaretle — sonraki istekler yeni generation ile çalışır
        with _analyze_gen_lock:
            _analyze_generation += 1
        logger.error(f"/analyze-review zma ({ANALYZE_TIMEOUT_SEC}s) — thread abandoned")
        raise HTTPException(
            status_code=504,
            detail=f"Analiz zaman aşımı (>{int(ANALYZE_TIMEOUT_SEC)}s). Karmaşık yorumlar için /review-intelligence/analyze kullanın.",
        )
    except Exception as e:
        logger.error(f"/analyze-review hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class HodipRequest(BaseModel):
    comment: str = Field(..., description="Müşteri yorumu")
    review_id: Optional[str] = Field(None, description="Yorum kimliği")
    rating: Optional[int] = Field(None, description="Yorum puanı (1-5)")
    language: Optional[str] = Field(None, description="Kaynak dil")

class HodipResponse(BaseModel):
    status: str
    message: str = ""
    hodip: Optional[dict] = None
    elapsed_ms: float = 0.0


@app.post("/hodip/analyze", response_model=HodipResponse, summary="HODIP — Derin Operasyonel Zeka Analizi")
async def hodip_analyze(request: HodipRequest):
    """Full HODIP pipeline: AOF → Knowledge Graph → Process Health → Escalation → Decision Report."""
    import time as _t
    t0 = _t.perf_counter()
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _SIDE_EXECUTOR,
            partial(
                hodip_engine.analyze,
                comment=request.comment,
                review_id=request.review_id or f"hodip-{hash(request.comment) & 0xFFFFFF:06x}",
                rating=request.rating,
                language=request.language or "tr",
            ),
        )
        elapsed = (_t.perf_counter() - t0) * 1000
        logger.info(f"/hodip/analyze ok {elapsed:.0f}ms facts={len(result.get('facts', {}))}")
        return HodipResponse(
            status="success",
            hodip=result,
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as e:
        logger.error(f"/hodip/analyze hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ReviewIntelligenceRequest(BaseModel):
    comment: str = Field(..., description="Müşteri yorumu")
    review_id: Optional[str] = Field(None, description="Yorum kimliği")
    rating: Optional[int] = Field(None, description="Yorum puanı (1-5)")
    language: Optional[str] = Field(None, description="Kaynak dil")
    metadata: Optional[dict] = Field(None, description="Ek metadata")


class ReviewIntelligenceBatchRequest(BaseModel):
    comments: List[str] = Field(..., description="Yorum listesi")
    metadata_list: Optional[List[dict]] = Field(None, description="Her yorum için metadata")


def _review_intelligence_sync(request: ReviewIntelligenceRequest) -> dict:
    result = review_intelligence_service.analyze(
        review_text=request.comment,
        review_id=request.review_id,
        metadata=request.metadata,
        language=request.language,
        rating=request.rating,
    )
    return result.to_dict()


@app.post("/review-intelligence/analyze", summary="DOC-004 Review Intelligence — Tam Pipeline")
async def review_intelligence_analyze(request: ReviewIntelligenceRequest):
    """14 aşamalı modular pipeline — ontology + ABSA adapter."""
    try:
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(_RI_EXECUTOR, _review_intelligence_sync, request),
            timeout=ANALYZE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.error(f"/review-intelligence/analyze zaman aşımı ({ANALYZE_TIMEOUT_SEC}s)")
        raise HTTPException(
            status_code=504,
            detail=f"Review Intelligence analizi {int(ANALYZE_TIMEOUT_SEC)} saniye içinde tamamlanamadı.",
        )
    except Exception as e:
        logger.error(f"/review-intelligence/analyze hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/review-intelligence/analyze-batch", summary="DOC-004 Review Intelligence — Toplu Analiz")
async def review_intelligence_analyze_batch(request: ReviewIntelligenceBatchRequest):
    try:
        translated = []
        for c in request.comments:
            tr, _ = TranslationService.translate_to_turkish(text=c)
            translated.append(tr)
        results = review_intelligence_service.analyze_batch(
            translated, metadata_list=request.metadata_list
        )
        return {"results": [r.to_dict() for r in results]}
    except Exception as e:
        logger.error(f"/review-intelligence/analyze-batch hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-absa", response_model=AbsaResponse, summary="ABSA — Çoklu Departman / Aspect Analizi")
async def analyze_absa(request: ReviewRequest):
    """Yorumu cümleciklere ayırır; her aspect için departman, duygu, öncelik ve Causal LLM açıklaması döner."""
    try:
        turkish_comment, _ = TranslationService.translate_to_turkish(
            text=request.comment,
            source_lang=request.language,
        )
        result = AbsaService.analyze(turkish_comment, rating=request.rating)
        data = AbsaService.to_dict(result)

        # Causal Deep Hotel LLM Zeka Katmanı ile Aspect Zenginleştirme
        try:
            llm_service = DeepHotelLLMService.get_instance()
            for asp in data.get("aspects", []):
                asp = llm_service.enrich_absa_aspect(asp)
                asp["llmExplanation"] = asp.get("llm_explanation")
                asp["llmStatus"] = asp.get("llm_status")
        except Exception as llm_err:
            logger.warning(f"Deep LLM enrichment skipped: {llm_err}")

        try:
            review_store.add_absa_aspects(f"absa-{hash(turkish_comment) & 0xFFFFFF:06x}", data.get("aspects", []))
        except Exception:
            logger.debug("analyze_absa: hata yutuldu", exc_info=True)
        return AbsaResponse(**data)
    except Exception as e:
        logger.error(f"/analyze-absa hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics/f1-report", response_model=SystemEvaluationReport, summary="Sistem F1 Score & Doğruluk Metrikleri Raporu")
@app.post("/metrics/evaluate", response_model=SystemEvaluationReport, summary="Sistem Metrik Değerlendirmesini Tetikle")
async def evaluate_system_metrics():
    """Canlı Sistem F1 Score, Hassasiyet (Precision), Duyarlılık (Recall), Başarım Oranı (Accuracy) ve LLM Kayıp Metriklerini Hesaplar."""
    try:
        loop = asyncio.get_running_loop()
        report = await loop.run_in_executor(_SIDE_EXECUTOR, EvalService.evaluate_system)
        return report
    except Exception as e:
        logger.error(f"/metrics/f1-report hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Hüseyin Backend Integration Endpoints (HTTP-only, no DB)
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    comment: str = Field(..., description="Otel yorumu")
    language: Optional[str] = Field(None, description="Dil kodu (tr/en/ru/de)")

class AnalyzeClause(BaseModel):
    clause: str
    aspectKey: str
    departmentKey: str
    sentiment: str
    priority: str
    suggestion: str = ""

class AnalyzeResponse(BaseModel):
    success: bool
    clauses: List[AnalyzeClause]
    error: Optional[str] = None

class BatchAnalyzeItem(BaseModel):
    comment: str
    language: Optional[str] = None

class BatchAnalyzeRequest(BaseModel):
    reviews: List[BatchAnalyzeItem]

class BatchAnalyzeResponse(BaseModel):
    success: bool
    results: List[AnalyzeResponse]
    error: Optional[str] = None

@app.post("/analyze", response_model=AnalyzeResponse, summary="Tekli yorum ABSA analizi (HTTP-only)")
async def analyze_single(request: AnalyzeRequest):
    """Hüseyin: HTTP-only endpoint, DB yazma yok. Her clause için aspect/department/sentiment/priority/suggestion döner."""
    from app.absa_platform.absa_engine import analyze_text
    import time
    t0 = time.time()
    try:
        # Translate to Turkish if needed
        if request.language and request.language.lower() != "tr":
            try:
                turkish_comment, _ = TranslationService.translate_to_turkish(
                    text=request.comment,
                    source_lang=request.language,
                )
            except Exception:
                turkish_comment = request.comment
        else:
            turkish_comment = request.comment

        results = analyze_text(turkish_comment)
        clauses = []
        for r in results:
            clauses.append(AnalyzeClause(
                clause=r.get("text", ""),
                aspectKey=r.get("aspect", "general"),
                departmentKey=r.get("department", "Otel Atmosferi & Misafir Profili"),
                sentiment=r.get("sentiment", "NOTR"),
                priority=r.get("priority", "DUSUK"),
                suggestion=r.get("suggestion", ""),
            ))
        return AnalyzeResponse(success=True, clauses=clauses)
    except Exception as e:
        logger.error(f"/analyze hatası: {e}")
        return AnalyzeResponse(success=False, clauses=[], error=str(e))

@app.post("/analyze/batch", response_model=BatchAnalyzeResponse, summary="Toplu yorum analizi (HTTP-only)")
async def analyze_batch_endpoint(request: BatchAnalyzeRequest):
    """Hüseyin: toplu analiz, her yorum bağımsız işlenir."""
    results = []
    for item in request.reviews:
        inner_req = AnalyzeRequest(comment=item.comment, language=item.language)
        res = await analyze_single(inner_req)
        results.append(res)
    return BatchAnalyzeResponse(success=True, results=results)


# ---------------------------------------------------------------------------
# Pelinsu Backend Integration (flat ReviewResponse format)
# ---------------------------------------------------------------------------
# Girdi: { comment, rating?, language? }
# Çıktı: { sentiment, sentimentScore, category, keywords[], summary, suggestion, confidence }
@app.post("/analyze-review", summary="Hızlı analiz (flat format) — Pelinsu")
async def analyze_review_fast(request: ReviewRequest):
    """Hızlı ABSA pipeline + BERTurk. sentiment, category, keywords, summary, suggestion, confidence döner."""
    from app.services.absa_service import AbsaService
    from collections import Counter
    turkish_comment, _ = TranslationService.translate_to_turkish(
        text=request.comment, source_lang=request.language,
    )
    multi_res = AbsaService.analyze_multidomain(turkish_comment, rating=request.rating)
    dict_res = AbsaService.to_multidomain_dict(multi_res)
    aspects = dict_res.get("aspects", [])

    if not aspects:
        return ReviewResponse(
            sentiment="Neutral", sentimentScore=0.0, category="Genel",
            keywords=[], summary="", suggestion="", confidence=0.5,
        )
    dept_counter = Counter(a["departmentLabel"] for a in aspects)
    primary_dept = dept_counter.most_common(1)[0][0]
    avg_score = dict_res.get("overallScore", 0.0)
    sent = dict_res.get("overallSentiment", "Neutral")

    keywords = []
    for a in aspects:
        kw = a.get("aspectLabel", "") or a.get("aspect", "")
        if kw and kw.lower() not in ("genel", "general", ""):
            keywords.append(kw)
    keywords = list(dict.fromkeys(keywords))[:6]

    good = [a['clause'] for a in aspects if len(a['clause']) > 20]
    if not good:
        good = [a['clause'] for a in aspects]
    summary = " | ".join(g[:80] for g in good[:3])
    suggestion = aspects[0].get("suggestion", "") if aspects else ""
    conf = sum(a.get("confidence", 0.8) for a in aspects) / len(aspects)

    secondary = None
    if len(dept_counter) > 1:
        secondary = dept_counter.most_common(2)[1][0]

    return ReviewResponse(
        sentiment=sent, sentimentScore=round(avg_score, 2),
        category=primary_dept, keywords=keywords,
        summary=summary, suggestion=suggestion, confidence=round(conf, 2),
        isMixedReview=len(dept_counter) > 1, secondaryCategory=secondary,
        userRating=request.rating,
        absaAspects=aspects,
        absaDepartmentSummary=dict_res.get("departmentSummary", {}),
    )


@app.post("/analyze-batch", summary="Toplu analiz (flat format) — Pelinsu")
async def analyze_batch_fast(request: BatchReviewRequest):
    results = []
    for item in request.comments:
        res = await analyze_review_fast(item)
        results.append(res)
    return BatchReviewResponse(analysis_results=results)


@app.post("/analyze-multidomain", response_model=MultiDomainAbsaResponse, summary="Çok Alanlı Ontology ABSA")
async def analyze_multidomain(request: MultiDomainReviewRequest):
    """Ontology-driven çok alanlı aspect analizi — domain, departman, memnuniyet."""
    try:
        turkish_comment, _ = TranslationService.translate_to_turkish(
            text=request.comment,
            source_lang=request.language,
        )
        result = AbsaService.analyze_multidomain(
            turkish_comment,
            rating=request.rating,
            domain_hint=request.domainHint,
        )
        data = AbsaService.to_multidomain_dict(result)
        try:
            entity_tracker_service.register_from_comment(turkish_comment)
        except Exception:
            logger.debug("analyze_multidomain: hata yutuldu", exc_info=True)
        return MultiDomainAbsaResponse(**data)
    except Exception as e:
        logger.error(f"/analyze-multidomain hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ontology/domains", summary="Ontology — tüm alanlar")
def ontology_domains():
    return {"domains": OntologyService.list_domains(), "count": len(OntologyService.list_domains())}


@app.get("/ontology/departments", summary="Ontology — alan departmanları")
def ontology_departments(domain: str):
    """domain=banka veya domain=finans ile departman listesi."""
    depts = OntologyService.get_departments(domain)
    if not depts:
        dom = OntologyService.get_domain(domain)
        if not dom:
            raise HTTPException(status_code=404, detail=f"Alan bulunamadı: {domain}")
        depts = dom.get("departments", [])
    return {"domain": domain, "departments": depts, "count": len(depts)}


@app.get("/ontology/domains/{domain_id}", summary="Ontology — alan detayı")
def ontology_domain_detail(domain_id: str):
    dom = OntologyService.get_domain(domain_id)
    if not dom:
        raise HTTPException(status_code=404, detail=f"Alan bulunamadı: {domain_id}")
    return dom



@app.post("/ocr-image", response_model=OcrResponse, summary="Görsel Netlik ve Metin Okuma (OCR)")
async def ocr_image(image: UploadFile = File(...)):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Geçersiz görsel dosyası.")
    try:
        image_bytes = await image.read()
        result = OcrService.process_image(image_bytes)
        return OcrResponse(**result)
    except Exception as e:
        logger.error(f"/ocr-image hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/info", summary="RAG Chatbot Veri Kaynağı Bilgisi")
def chat_info():
    # Yükleme sürerken bloke etme / ikinci joblib.load tetikleme
    return RagService.get_index_info_fast()

@app.post("/chat", response_model=ChatResponse, summary="RAG Tabanlı Akıllı Chatbot (Hotel Agent entegre)")
async def chat_endpoint(request: ChatRequest):
    try:
        agent_result = await HotelAgentService.process_query(
            query=request.query,
            api_key=request.api_key,
            session_id=request.session_id,
            role=request.role,
        )
        rag_meta = agent_result.get("rag_meta") or {}
        return ChatResponse(
            response=agent_result.get("answer", ""),
            data_source=", ".join(agent_result.get("sources", [])) or rag_meta.get("data_source"),
            indexed_records=rag_meta.get("indexed_records"),
            matches_found=rag_meta.get("matches_found"),
            mode=agent_result.get("mode"),
            intent=agent_result.get("intent"),
            department=agent_result.get("department"),
            priority=agent_result.get("priority"),
            action_required=agent_result.get("action_required"),
            sources=agent_result.get("sources"),
            room_number=(agent_result.get("entities") or {}).get("room_number"),
        )
    except Exception as e:
        logger.error(f"/chat hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hotel/profile", summary="Mevcut otel profili")
def hotel_profile():
    return HotelKnowledgeService.load_profile()


@app.put("/hotel/profile", summary="Otel profilini güncelle (admin)")
def hotel_profile_update(body: HotelProfileUpdate):
    try:
        updated = HotelKnowledgeService.save_profile(body.profile)
        return {"status": "ok", "profile": updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/ops/chat", response_model=OpsChatResponse, summary="Ops Copilot — Planner + Tools pipeline")
async def ops_chat_endpoint(request: OpsChatRequest):
    """Staff ops sorgularını Gateway → Planner → Tools üzerinden işler."""
    try:
        adapter = get_ops_copilot_adapter()
        q = (request.query or "").strip()
        _ops_followup = request.session_id and (
            re.fullmatch(r"\d{3,4}", q)
            or normalize_turkish(q.lower()) in ("evet", "tamam", "olur", "klima", "su", "wifi")
        )
        if not OpsCopilotAdapter.is_ops_query(request.query) and not _ops_followup:
            fallback = await HotelAgentService.process_query(
                query=request.query,
                session_id=request.session_id,
                role=request.role,
            )
            return OpsChatResponse(
                answer=fallback.get("answer", ""),
                mode=fallback.get("mode", "fallback"),
                intent=fallback.get("intent"),
                department=fallback.get("department"),
                priority=fallback.get("priority"),
                action_required=fallback.get("action_required"),
            )
        result = adapter.process(
            request.query,
            role=request.role,
            hotel_id=request.hotel_id or "h1",
            session_id=request.session_id,
        )
        meta = result.get("ops_meta") or {}
        return OpsChatResponse(
            answer=result.get("answer", ""),
            mode=result.get("mode", "ops_copilot"),
            plan=meta.get("plan"),
            tool_results=meta.get("tool_results"),
            tools_used=meta.get("tools_used"),
            request_id=meta.get("request_id"),
            intent=result.get("intent"),
            department=result.get("department"),
            priority=result.get("priority"),
            action_required=result.get("action_required"),
        )
    except Exception as e:
        logger.error(f"/ops/chat hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/hotel/agent", response_model=HotelAgentResponse, summary="Otel AI Agent — birleşik sorgu")
async def hotel_agent_endpoint(request: HotelAgentRequest):
    try:
        result = await HotelAgentService.process_query(
            query=request.query,
            api_key=request.api_key,
            session_id=request.session_id,
            role=request.role,
        )
        return HotelAgentResponse(
            answer=result.get("answer", ""),
            intent=result.get("intent", "general_inquiry"),
            department=result.get("department", "Front Office"),
            priority=result.get("priority", "low"),
            action_required=bool(result.get("action_required")),
            sources=result.get("sources", []),
            mode=result.get("mode", "general"),
            entities=result.get("entities"),
            matched_question=result.get("matched_question"),
            confidence=result.get("confidence"),
            rag_meta=result.get("rag_meta"),
        )
    except Exception as e:
        logger.error(f"/hotel/agent hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hotel/faq", summary="Otel FAQ listesi")
def hotel_faq(department: Optional[str] = None):
    faqs = HotelKnowledgeService.get_all_faqs(department)
    return {"total": len(faqs), "department": department, "faqs": faqs}


@app.get("/hotel/intents", summary="Desteklenen intent listesi")
def hotel_intents():
    return {"intents": IntentService.list_intents(), "total": len(IntentService.list_intents())}

async def _run_analysis(comment: str, rating: int = None, api_key: str = None) -> ReviewResponse:
    turkish_comment, _ = TranslationService.translate_to_turkish(text=comment)
    is_manipulation = SentimentService.is_manipulation(turkish_comment, rating)
    sentiment, sentiment_score = SentimentService.analyze_sentiment(text=turkish_comment, rating=rating)
    category, confidence, class_method, secondary_cat, is_mixed = category_service.classify_category(
        turkish_comment, api_key, use_gemini=bool(api_key)
    )
    keywords = KeywordService.extract_keywords(turkish_comment, max_keywords=6)
    summary = RagService.generate_summary(turkish_comment)
    suggestion = RagService.generate_suggestion(
        category=category,
        text=turkish_comment,
        keywords=keywords,
        sentiment=sentiment,
        is_mixed=is_mixed,
        secondary_category=secondary_cat,
        is_manipulation=is_manipulation,
    )
    predicted_rating = None
    if rating is None:
        predicted_rating = SentimentService.predict_rating(turkish_comment, sentiment, sentiment_score)
    return ReviewResponse(
        sentiment=sentiment,
        sentimentScore=sentiment_score,
        category=category,
        keywords=keywords,
        summary=summary,
        suggestion=suggestion,
        confidence=confidence,
        predictedRating=predicted_rating,
        userRating=rating,
        classificationMethod=class_method,
        isManipulation=is_manipulation,
        isMixedReview=is_mixed,
        secondaryCategory=secondary_cat,
    )


def _analysis_to_dict(resp: ReviewResponse) -> dict:
    return {
        "sentiment": resp.sentiment,
        "sentimentScore": resp.sentimentScore,
        "category": resp.category,
        "confidence": resp.confidence,
        "keywords": resp.keywords,
        "summary": resp.summary,
        "suggestion": resp.suggestion,
        "isMixedReview": resp.isMixedReview,
        "secondaryCategory": resp.secondaryCategory,
        "isManipulation": resp.isManipulation,
    }


def _sync_analyze_for_store(comment: str, rating: Optional[int] = None) -> dict:
    """ReviewStore seed için senkron analiz wrapper."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        resp = loop.run_until_complete(_run_analysis(comment, rating))
        return _analysis_to_dict(resp)
    finally:
        loop.close()


def _warmup_services() -> None:
    """İlk istekte donmayı önlemek için hafif kaynakları önceden yükle (RAG ayrı, kilitli)."""
    try:
        SentimentService.analyze_sentiment("Oda temizdi.", rating=4)
        logger.info("Sentiment ön-ısındırıldı")
    except Exception as exc:
        logger.warning(f"Sentiment warmup atlandı: {exc}")
    try:
        category_service.classify_category("Yemekler lezzetliydi.", None, use_gemini=False)
        logger.info("Kategori ön-ısındırıldı")
    except Exception as exc:
        logger.warning(f"Kategori warmup atlandı: {exc}")
    try:
        AbsaService.analyze("Oda temizdi ama klima çalışmıyordu.", rating=3, multidomain=False)
        logger.info("ABSA hotel yolu ön-ısındırıldı")
    except Exception as exc:
        logger.warning(f"ABSA warmup atlandı: {exc}")
    try:
        RagService._load_index()
        logger.info("RAG indeksi ön-yüklendi")
    except Exception as exc:
        logger.warning(f"RAG ön-yükleme atlandı: {exc}")


def _seed_dashboard_demo_sync() -> None:
    try:
        n = review_store.seed_demo_if_empty(_sync_analyze_for_store)
        if n:
            logger.info(f"Dashboard demo seed: {n} yorum yuklendi")
        room_seed = room_issue_service.seed_demo_data(force=False)
        if room_seed.get("seeded"):
            logger.info(f"Oda sorun demo seed: {room_seed['seeded']} kayit")
        entity_seed = entity_tracker_service.seed_demo_data(force=False)
        if entity_seed.get("seeded"):
            logger.info(f"Entity tracker demo seed: {entity_seed['seeded']} kayit")
    except Exception as e:
        logger.warning(f"Dashboard seed atlandi: {e}")


@app.on_event("startup")
async def _startup_background_tasks():
    # Önce hafif warmup (sentiment/category/ABSA), RAG sonra — UI istekleri RAG'e bağımlı değil
    asyncio.create_task(asyncio.to_thread(_warmup_services))
    # Seed gecikmeli — ilk isteklerle GIL/CPU yarışmasın
    async def _delayed_seed():
        await asyncio.sleep(8)
        await asyncio.to_thread(_seed_dashboard_demo_sync)
    asyncio.create_task(_delayed_seed())


@app.get("/rooms/{room_number}/issues", summary="Oda — açık/çözülmüş sorunlar")
def room_issues(room_number: str, status: Optional[str] = None):
    if status == "resolved":
        items = room_issue_service.get_resolved_issues(room_number)
    elif status == "open":
        items = room_issue_service.get_open_issues(room_number)
    else:
        report = room_issue_service.get_room_report(room_number)
        return report
    return {
        "room_number": room_number,
        "status_filter": status,
        "issues": [i.to_dict() for i in items],
        "count": len(items),
    }


@app.get("/rooms/{room_number}/report", summary="Oda — tam operasyon raporu")
def room_report(room_number: str):
    return room_issue_service.get_room_report(room_number)


@app.get("/entities/{entity_id}/report", summary="Varlık — genelleştirilmiş operasyon raporu")
def entity_report(entity_id: str, entity_type: Optional[str] = None):
    """
    entity_id: room_504, kadikoy_subesi veya 504 (oda numarası)
    """
    if entity_type == "room" or (entity_id.isdigit() and len(entity_id) in (3, 4)):
        eid = f"room_{entity_id}" if entity_id.isdigit() else entity_id
        return entity_tracker_service.get_entity_report(eid)
    if entity_id.startswith("room_") or ":" in entity_id:
        return entity_tracker_service.get_entity_report(entity_id.replace("room:", "room_"))
    return entity_tracker_service.get_entity_report(entity_id)


@app.get("/rooms/patterns", summary="Çapraz oda sorun desenleri")
def room_patterns(issue: str = "klima", days: int = 7):
    patterns = room_issue_service.find_cross_room_patterns(issue, days=days)
    return {
        "issue_type": issue,
        "days": days,
        "pattern_count": len(patterns),
        "systemic_warning": len(patterns) >= 2,
        "rooms": patterns,
    }


@app.post("/rooms/seed", summary="Demo oda sorun verisi yükle")
def rooms_seed(force: bool = False):
    return room_issue_service.seed_demo_data(force=force)


@app.post("/scrape-reviews/playwright", response_model=ScrapeResponse, summary="Google Maps Playwright ile Yorum Kazıma (1500+ yorum)")
async def scrape_reviews_playwright_endpoint(request: PlaywrightScrapeRequest):
    """Google Maps URL'ini Playwright (headless Chromium) ile açar,
    tüm yorumları kaydırarak toplar ve AI analizinden geçirir.
    1500+ yorum / sıralama, --all-sorts ile 6000+ yorum toplar."""
    from app.services.scraper_adapters import get_adapter
    adapter = get_adapter("google_maps_playwright")
    result = adapter.fetch_reviews(
        hotel_query="",
        options={
            "url": request.url,
            "limit": request.max_reviews,
            "all_sorts": request.all_sorts,
        },
    )
    if result.error and not result.warning:
        result.warning = result.error

    items: List[ScrapedReviewItem] = []
    max_analyze = request.max_reviews if request.max_reviews > 0 else 20
    for idx, review in enumerate(result.reviews):
        analysis = None
        if request.analyze and review.comment and idx < max_analyze:
            ar = await _run_analysis(review.comment, int(review.rating) if review.rating else None, request.api_key)
            analysis = ScrapedReviewAnalysis(
                sentiment=ar.sentiment,
                sentimentScore=ar.sentimentScore,
                category=ar.category,
                keywords=ar.keywords,
                summary=ar.summary,
                suggestion=ar.suggestion,
                confidence=ar.confidence,
            )
        items.append(ScrapedReviewItem(
            guest_name=review.guest_name,
            comment=review.comment,
            rating=int(review.rating) if review.rating else None,
            source="Google Maps (Playwright)",
            platform="google_maps_playwright",
            review_date=review.date,
            language=review.language or "",
            analysis=analysis,
        ))

    return ScrapeResponse(
        reviews=items,
        total=len(items),
        method=result.method or "playwright_browser",
        source_detected="google_maps_playwright",
        warning=result.warning,
    )


@app.post("/scrape-reviews", response_model=ScrapeResponse, summary="İnternetten Otel Yorumu Kazıma + AI Etiketleme")
async def scrape_reviews_endpoint(request: ScrapeRequest):
    try:
        google_key = request.google_places_api_key or request.google_api_key
        per_source_limit = request.max_per_source or request.limit

        # sources dict formatı: {"booking": "url", ...}
        merged_urls = dict(request.urls or request.source_urls or {})
        if request.google_place_id:
            merged_urls["google"] = request.google_place_id
            merged_urls["google_place_id"] = request.google_place_id

        # sources dict'ten kaynak listesi türet
        source_list = request.sources
        if not source_list and merged_urls:
            source_list = list(merged_urls.keys())
            if "google_place_id" in source_list:
                source_list.remove("google_place_id")

        # Çoklu kaynak modu
        if source_list and len(source_list) > 0:
            multi_result = MultiScraperService.scrape_hotel(
                name=request.hotel_name or request.url or "Hotel",
                city=request.city or "",
                country=request.country or "",
                sources=source_list,
                urls=merged_urls,
                options={
                    "limit": per_source_limit,
                    "analyze": request.analyze,
                    "allow_fallback": request.allow_fallback,
                    "api_key": request.api_key,
                    "google_places_api_key": google_key,
                    "csv_path": request.csv_path,
                    "url": request.url,
                    "place_id": request.google_place_id,
                    "hotel_name": request.hotel_name,
                },
            )
            return _multi_to_scrape_response(multi_result)

        if not request.url and not request.csv_path:
            raise HTTPException(status_code=400, detail="url, csv_path veya sources[] gerekli.")
        scrape_result = ScraperService.scrape_reviews(
            url=request.url or "",
            limit=request.limit,
            allow_fallback=request.allow_fallback,
            google_api_key=request.google_places_api_key,
            csv_path=request.csv_path,
        )
        items: List[ScrapedReviewItem] = []
        for raw in scrape_result["reviews"]:
            analysis = None
            if request.analyze and raw.get("comment"):
                ar = await _run_analysis(raw["comment"], raw.get("rating"), request.api_key)
                analysis = ScrapedReviewAnalysis(
                    sentiment=ar.sentiment,
                    sentimentScore=ar.sentimentScore,
                    category=ar.category,
                    keywords=ar.keywords,
                    summary=ar.summary,
                    suggestion=ar.suggestion,
                    confidence=ar.confidence,
                )
            items.append(ScrapedReviewItem(
                guest_name=raw.get("guest_name", "Anonim"),
                comment=raw.get("comment", ""),
                rating=raw.get("rating"),
                source=raw.get("source", "unknown"),
                review_date=raw.get("review_date"),
                analysis=analysis,
            ))
        return ScrapeResponse(
            reviews=items,
            total=len(items),
            method=scrape_result["method"],
            source_detected=scrape_result["source_detected"],
            warning=scrape_result.get("warning"),
        )
    except Exception as e:
        logger.error(f"/scrape-reviews hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _multi_to_scrape_response(multi_result: dict) -> ScrapeResponse:
    """MultiScraper sonucunu geriye uyumlu ScrapeResponse'a çevir."""
    from app.services.review_source_schema import Platform, PLATFORM_BADGE_COLORS, PLATFORM_DISPLAY_NAMES

    items: List[ScrapedReviewItem] = []
    for raw in multi_result.get("reviews", []):
        a = raw.get("analysis") or {}
        analysis = ScrapedReviewAnalysis(
            sentiment=a.get("sentiment", "Neutral"),
            sentimentScore=a.get("sentiment_score", 0.0),
            category=a.get("category", a.get("department", "")),
            keywords=a.get("keywords") or [],
            summary=a.get("summary", ""),
            suggestion=a.get("action_item") or a.get("suggested_response", ""),
            confidence=a.get("confidence", 0.0),
        ) if a else None
        plat = Platform.from_string(raw.get("platform", "")).value
        items.append(ScrapedReviewItem(
            guest_name=raw.get("guest_name", "Anonim"),
            comment=raw.get("comment", ""),
            rating=int(raw.get("rating")) if raw.get("rating") else None,
            source=raw.get("platform", "unknown"),
            review_date=raw.get("date"),
            platform=plat,
            language=raw.get("language", ""),
            helpful_count=int(raw.get("helpful_count") or 0),
            is_most_helpful=bool(raw.get("is_most_helpful")),
            badge_color=PLATFORM_BADGE_COLORS.get(plat, "#6B7280"),
            badge_label=PLATFORM_DISPLAY_NAMES.get(plat, raw.get("platform", "")),
            title=raw.get("title", ""),
            analysis=analysis,
        ))
    warning_parts = multi_result.get("warnings", []) + multi_result.get("errors", [])
    return ScrapeResponse(
        reviews=items,
        total=multi_result.get("total", 0),
        method=",".join(multi_result.get("methods", ["multi"])),
        source_detected=",".join(multi_result.get("sources_succeeded", [])),
        warning=" | ".join(warning_parts) if warning_parts else None,
        source_stats=multi_result.get("source_stats"),
        sources_succeeded=multi_result.get("sources_succeeded"),
    )


@app.post("/scrape-reviews/multi", response_model=MultiScrapeResponse, summary="Çok Platformlu Yorum Kazıma")
async def scrape_reviews_multi_endpoint(request: MultiScrapeRequest):
    try:
        result = MultiScraperService.scrape_hotel(
            name=request.hotel_name,
            city=request.city,
            country=request.country,
            sources=request.sources,
            urls=request.urls or {},
            options={
                "limit": request.limit,
                "analyze": request.analyze,
                "allow_fallback": request.allow_fallback,
                "api_key": request.api_key,
                "google_places_api_key": request.google_places_api_key,
                "csv_path": request.csv_path,
                "column_mapping": request.column_mapping,
            },
        )
        reviews = [IngestedReviewItem(**r) for r in result.get("reviews", [])]
        return MultiScrapeResponse(reviews=reviews, **{k: result[k] for k in MultiScrapeResponse.model_fields if k != "reviews"})
    except Exception as e:
        logger.error(f"/scrape-reviews/multi hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scraper/sources", summary="Kullanılabilir Kazıma Kaynakları + Yasal Durum")
@app.get("/scrape/platforms", summary="Desteklenen Platformlar + Durum (alias)")
def scraper_sources():
    platforms = MultiScraperService.list_sources()
    return {
        "sources": platforms,
        "platforms": platforms,
        "total": len(platforms),
        "documentation": "simulation/SCRAPING_GUIDE.md",
    }

@app.post("/import-reviews-csv", response_model=ScrapeResponse, summary="CSV Dosyasından Yorum İçe Aktarma + AI Etiketleme")
async def import_reviews_csv_endpoint(
    file: UploadFile = File(...),
    limit: int = 10,
    analyze: bool = True,
    api_key: Optional[str] = None,
    platform: Optional[str] = None,
    column_mapping: Optional[str] = None,
):
    """Tarayıcıdan yüklenen CSV dosyasını geçici kaydedip analiz eder."""
    import tempfile
    import json as _json
    try:
        suffix = ".csv"
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Boş dosya.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        mapping = None
        if column_mapping:
            try:
                mapping = _json.loads(column_mapping)
            except _json.JSONDecodeError:
                logger.debug("import_reviews_csv_endpoint: hata yutuldu", exc_info=True)
        try:
            result = MultiScraperService.scrape_hotel(
                name=platform or "CSV Import",
                sources=["csv"],
                options={
                    "limit": max(1, min(limit, 100)),
                    "analyze": analyze,
                    "api_key": api_key,
                    "csv_path": tmp_path,
                    "platform": platform or "CSV Import",
                    "column_mapping": mapping,
                    "allow_fallback": False,
                },
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.debug("import_reviews_csv_endpoint: hata yutuldu", exc_info=True)
        return _multi_to_scrape_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/import-reviews-csv hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collector/template", summary="Boş Yorum Toplayıcı CSV Şablonu")
def collector_template():
    """Collector CSV sütun başlıklarını içeren boş şablon."""
    return PlainTextResponse(
        content=get_csv_template(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="review_collector_template.csv"'},
    )


@app.post("/collector/paste", response_model=CollectorPasteResponse, summary="Yapıştırılmış Yorumları CSV'ye Kaydet + Analiz")
async def collector_paste_endpoint(request: CollectorPasteRequest):
    """UI veya API'den yapıştırılan yorum bloklarını parse eder, CSV'ye yazar ve opsiyonel analiz eder."""
    try:
        result = import_paste_text(
            text=request.text,
            hotel_name=request.hotel_name,
            country=request.country,
            city=request.city,
            platform=request.platform,
        )
        if not result.get("success"):
            return CollectorPasteResponse(
                success=False,
                error=result.get("error", "Parse hatası"),
            )

        analysis_total = None
        analysis_reviews = None
        if request.analyze and result.get("path"):
            try:
                analysis = analyze_collected_csv(
                    csv_path=result["path"],
                    hotel_name=request.hotel_name,
                    platform=request.platform,
                    limit=request.limit,
                    analyze=True,
                    api_key=request.api_key,
                )
                analysis_total = analysis.get("total", 0)
                analysis_reviews = analysis.get("reviews", [])
            except Exception as e:
                logger.warning(f"Collector analiz hatası: {e}")

        return CollectorPasteResponse(
            success=True,
            count=result.get("count", 0),
            skipped_dup=result.get("skipped_dup", 0),
            path=result.get("path", ""),
            preview=result.get("preview", []),
            analysis_total=analysis_total,
            analysis_reviews=analysis_reviews,
            format_detected=result.get("format_detected"),
        )
    except Exception as e:
        logger.error(f"/collector/paste hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collector/import-bulk", response_model=CollectorPasteResponse, summary="Google/TripAdvisor Bulk Yapıştır → CSV + Analiz")
async def collector_import_bulk_endpoint(request: CollectorBulkRequest):
    """Google Maps veya TripAdvisor'dan kopyalanan toplu yorumları ayrıştırır."""
    try:
        result = import_bulk_paste(
            text=request.text,
            hotel_name=request.hotel_name,
            country=request.country,
            city=request.city,
            force=request.force,
            analyze=request.analyze,
            limit=request.limit,
            api_key=request.api_key,
        )
        if not result.get("success"):
            return CollectorPasteResponse(
                success=False,
                error=result.get("error", "Parse hatası"),
            )
        return CollectorPasteResponse(
            success=True,
            count=result.get("count", 0),
            skipped_dup=result.get("skipped_dup", 0),
            path=result.get("path", ""),
            preview=result.get("preview", []),
            analysis_total=result.get("analysis_total"),
            analysis_reviews=result.get("analysis_reviews"),
            format_detected=result.get("format_detected", "google_bulk"),
        )
    except Exception as e:
        logger.error(f"/collector/import-bulk hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/entities/seed", summary="Demo entity sorun verisi yükle")
def entities_seed(force: bool = False):
    return entity_tracker_service.seed_demo_data(force=force)


@app.get("/entities/patterns", summary="Çapraz entity sorun desenleri")
def entity_patterns(issue: str = "wifi", days: int = 7, entity_type: Optional[str] = None):
    patterns = entity_tracker_service.find_cross_entity_patterns(issue, entity_type=entity_type, days=days)
    return {
        "issue_type": issue,
        "days": days,
        "entity_type": entity_type,
        "pattern_count": len(patterns),
        "entities": patterns,
    }


@app.get("/dashboard/stats", summary="Yönetici Dashboard — İstatistikler")
def dashboard_stats(role: Optional[str] = None, domain: Optional[str] = None):
    return AnalyticsService.compute_stats(role=role, domain=domain)

@app.get("/dashboard/recommendations", summary="Yönetici Dashboard — Departman Önerileri")
def dashboard_recommendations(role: Optional[str] = None):
    return {"recommendations": AnalyticsService.department_recommendations(role=role)}

@app.get("/dashboard/summary", summary="Yönetici Dashboard — Yönetici Özeti")
def dashboard_summary(role: Optional[str] = None):
    return {"executive_summary": AnalyticsService.executive_summary(role=role)}

@app.get("/dashboard/chatbot-stats", summary="Yönetici Dashboard — Chatbot/RAG İstatistikleri")
def dashboard_chatbot_stats():
    return AnalyticsService.chatbot_stats()

@app.get("/dashboard/full", summary="Yönetici Dashboard — Tam Rapor")
def dashboard_full(role: Optional[str] = None):
    return AnalyticsService.full_dashboard(role=role)

@app.post("/dashboard/seed", summary="Demo yorumları yükle/yenile")
def dashboard_seed(force: bool = False):
    from app.services.review_store import DEMO_REVIEWS
    if force:
        review_store.clear()
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        total = len(DEMO_REVIEWS)
        for i, (comment, rating) in enumerate(DEMO_REVIEWS):
            days_ago = 13 - int(i * 13 / max(total - 1, 1))
            created = (now - timedelta(days=days_ago, hours=i % 8)).isoformat()
            review_store.add_from_analysis(
                comment, rating, _sync_analyze_for_store(comment, rating), source="demo", created_at=created
            )
        return {"seeded": len(DEMO_REVIEWS), "total": review_store.count()}
    added = review_store.seed_demo_if_empty(_sync_analyze_for_store)
    return {"seeded": added, "total": review_store.count()}

@app.get("/dashboard/reviews", summary="Depolanmış yorum listesi")
def dashboard_reviews(limit: int = 50, offset: int = 0):
    items = review_store.all_reviews()
    slice_ = items[offset: offset + limit]
    return {
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "reviews": [r.to_dict() for r in slice_],
    }

@app.post("/retrain", summary="Yapay Sinir Ağını Düzeltilmiş Verilerle Yeniden Eğit")
async def retrain_endpoint(request: RetrainRequest):
    try:
        # Pydantic modellerini dict listesine çevir
        data_dicts = [item.dict() for item in request.data]
        
        result = category_service.retrain_model(data_dicts)
        if result["status"] == "success":
            return result
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        logger.error(f"/retrain hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learn/feedback", summary="Kullanıcı düzeltmesi — 3x ağırlıklı öğrenme")
async def learn_feedback_endpoint(request: LearnFeedbackRequest):
    try:
        return feedback_service.submit_correction(
            review_id=request.review_id,
            correct_category=request.correct_category,
            correct_sentiment=request.correct_sentiment,
            notes=request.notes or "",
        )
    except Exception as e:
        logger.error(f"/learn/feedback hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learn/retrain", summary="Learning buffer'dan incremental retrain")
async def learn_retrain_endpoint(request: LearnRetrainRequest):
    try:
        result = learning_service.run_retrain(
            category_service=category_service,
            force=request.force,
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/learn/retrain hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/learn/stats", summary="Öğrenme istatistikleri")
def learn_stats_endpoint():
    return learning_service.get_stats()


@app.get("/learn/buffer", summary="Son öğrenilen örnekler (admin)")
def learn_buffer_endpoint(limit: int = 20):
    return {
        "total": learning_service.get_buffer_size(),
        "samples": learning_service.get_recent_buffer(limit=min(limit, 100)),
    }


@app.post("/learning/bulk-train", summary="Tüm kaynaklardan toplu ABSA eğitimi")
async def learning_bulk_train_endpoint(request: BulkTrainRequest):
    try:
        from app.services.bulk_trainer import get_bulk_trainer
        from app.services.ontology_service import reload_ontology
        reload_ontology()
        trainer = get_bulk_trainer(reviews_dir=request.reviews_dir)
        result = trainer.run_bulk_train(
            include_long=request.include_long,
            retrain_absa=request.retrain_absa,
            export_weights=request.export_weights,
            include_mega=request.include_mega,
            mega_limit=request.mega_limit,
            category_service=category_service,
        )
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"/learning/bulk-train hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learning/train-from-csv", summary="Tek CSV dosyasından bulk eğitim")
async def learning_train_from_csv_endpoint(request: TrainFromCsvRequest):
    try:
        if not os.path.isfile(request.csv_path):
            raise HTTPException(status_code=404, detail=f"CSV bulunamadı: {request.csv_path}")
        from app.services.bulk_trainer import get_bulk_trainer
        from app.services.ontology_service import reload_ontology
        reload_ontology()
        trainer = get_bulk_trainer()
        result = trainer.train_from_csv(
            csv_path=request.csv_path,
            include_long=request.include_long,
            retrain_absa=request.retrain_absa,
            export_weights=request.export_weights,
            category_service=category_service,
        )
        return {"status": "success", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/learning/train-from-csv hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learning/retrain", summary="Learning buffer + eğitim verisinden retrain")
async def learning_retrain_endpoint(request: LearnRetrainRequest):
    try:
        result = learning_service.run_retrain(
            category_service=category_service,
            force=request.force,
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/learning/retrain hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/learning/stats", summary="Öğrenme istatistikleri (buffer + training)")
def learning_stats_endpoint():
    from app.services.incremental_trainer import get_incremental_trainer
    from app.services.learning_store import get_learning_store
    stats = learning_service.get_stats()
    stats["incremental_trainer"] = get_incremental_trainer().get_training_stats()
    stats["feedback_store"] = get_learning_store().get_stats()
    return stats


@app.get("/learning/training-data", summary="Eğitim verisi export")
def learning_training_data_endpoint():
    from app.services.incremental_trainer import get_incremental_trainer
    return get_incremental_trainer().export_training_data()

# ---------------------------------------------------------------------------
# Test DB endpoints — lokal SQLite, manuel test ve düzeltme için
# ---------------------------------------------------------------------------
from pydantic import Field as PydanticField

class TestSubmitRequest(BaseModel):
    comment: str = Field(..., description="Yorum metni")
    rating: Optional[int] = Field(None, ge=1, le=5)
    language: Optional[str] = "tr"

class TestCorrectionRequest(BaseModel):
    corrected_department: Optional[str] = ""
    corrected_sentiment: Optional[str] = ""
    notes: Optional[str] = ""
    corrected_aspects: Optional[List[dict]] = []

@app.on_event("startup")
async def _init_test_db():
    from app.services.test_db_service import init_db
    init_db()

@app.post("/test/submit", summary="Test yorumu gönder ve analiz et")
async def test_submit(request: TestSubmitRequest):
    from app.services.test_db_service import add_review
    inner = ReviewRequest(comment=request.comment, rating=request.rating, language=request.language)
    result = await analyze_review_fast(inner)
    review_id = add_review(request.comment, request.rating, request.language or "tr", result.dict())
    return {"id": review_id, "analysis": result.dict()}

@app.get("/test/reviews", summary="Test yorumlarını listele")
def test_list(limit: int = 50, offset: int = 0, uncorrected_only: bool = False):
    from app.services.test_db_service import list_reviews
    rows, total = list_reviews(limit, offset, uncorrected_only)
    return {"total": total, "reviews": rows}

@app.get("/test/reviews/{review_id}", summary="Test yorum detayı")
def test_get(review_id: int):
    from app.services.test_db_service import get_review
    r = get_review(review_id)
    if not r:
        raise HTTPException(404, "Review not found")
    return r

@app.post("/test/correct/{review_id}", summary="Test yorumunu düzelt")
def test_correct(review_id: int, correction: TestCorrectionRequest):
    from app.services.test_db_service import correct_review
    ok = correct_review(review_id, correction.dict())
    if not ok:
        raise HTTPException(404, "Review not found")
    return {"status": "ok"}

@app.delete("/test/reviews/{review_id}", summary="Test yorumunu sil")
def test_delete(review_id: int):
    from app.services.test_db_service import delete_review
    ok = delete_review(review_id)
    if not ok:
        raise HTTPException(404, "Review not found")
    return {"status": "deleted"}

@app.get("/test/export", summary="Düzeltilmiş yorumları dışa aktar")
def test_export():
    from app.services.test_db_service import export_corrected
    return {"corrected_reviews": export_corrected()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
   