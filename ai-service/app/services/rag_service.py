import os
import re
import asyncio
import logging
import threading
from typing import Optional

import joblib
import requests
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("ai_service")

# Proje kökü: ai-service/app/services → ../../.. = KodYazılımStaj1
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SIM_DIR = os.path.join(_PROJECT_ROOT, "simulation")
_RAG_INDEX_PATH = os.path.join(_SIM_DIR, "rag_index.joblib")

# joblib yoksa okunacak yedek CSV'ler
_FALLBACK_CSVS = [
    os.path.join(_SIM_DIR, "processed_reviews_25k.csv"),
    os.path.join(_SIM_DIR, "synthetic_reviews.csv"),
    os.path.join(_SIM_DIR, "crystal_waterworld_analyzed_reviews.csv"),
    os.path.join(_SIM_DIR, "scraped_analyzed_reviews.csv"),
]

_TEXT_COLUMNS = ("translated_comment", "original_comment", "comment", "text", "review")
_TOP_K = 5

gemini_semaphore = asyncio.Semaphore(2)

# Bellek içi önbellek — çift joblib.load yarışını kilit ile önle (GIL 4–30s bloke)
_index_cache: Optional[dict] = None
_index_lock = threading.Lock()
_index_loading = False


class RagService:
    # ------------------------------------------------------------------ #
    #  İndeks yükleme
    # ------------------------------------------------------------------ #
    @classmethod
    def is_index_ready(cls) -> bool:
        return _index_cache is not None

    @classmethod
    def _load_index(cls) -> dict:
        global _index_cache, _index_loading
        if _index_cache is not None:
            return _index_cache

        with _index_lock:
            if _index_cache is not None:
                return _index_cache
            _index_loading = True
            try:
                if os.path.isfile(_RAG_INDEX_PATH):
                    try:
                        loaded = joblib.load(_RAG_INDEX_PATH)
                        _index_cache = loaded
                        n = loaded.get("meta", {}).get("indexed_records", len(loaded.get("records", [])))
                        logger.info(f"RAG indeksi yüklendi: {n:,} kayıt ({_RAG_INDEX_PATH})")
                        return _index_cache
                    except Exception as e:
                        logger.warning(f"rag_index.joblib okunamadı: {e}")

                # joblib yok — CSV'den geçici indeks oluştur
                _index_cache = cls._build_runtime_index_from_csvs()
                return _index_cache
            finally:
                _index_loading = False

    @classmethod
    def get_index_info_fast(cls) -> dict:
        """UI/chat info — yükleme sürüyorsa bloke etme (çift RAG load tetikleme)."""
        if _index_cache is not None:
            return cls.get_index_info()
        if _index_loading:
            return {
                "indexed_records": 0,
                "source_stats": {},
                "total_source_estimate": "RAG yükleniyor…",
                "index_path": _RAG_INDEX_PATH,
                "loading": True,
            }
        return cls.get_index_info()

    @classmethod
    def _build_runtime_index_from_csvs(cls) -> dict:
        records = []
        source_stats = {}
        for path in _FALLBACK_CSVS:
            if not os.path.isfile(path):
                continue
            try:
                df = pd.read_csv(path)
                text_col = next((c for c in _TEXT_COLUMNS if c in df.columns), None)
                if not text_col:
                    continue
                count = 0
                for _, row in df.iterrows():
                    text = str(row.get(text_col, "") or "").strip()
                    if len(text) < 3:
                        continue
                    rating = row.get("rating", "N/A")
                    records.append({
                        "_rag_text": text,
                        "category": str(row.get("category", "Bilinmiyor")),
                        "rating": rating,
                        "sentiment": str(row.get("sentiment", "")),
                        "source": str(row.get("source", os.path.basename(path))),
                        "_origin": os.path.basename(path),
                    })
                    count += 1
                source_stats[os.path.basename(path)] = count
            except Exception as e:
                logger.warning(f"CSV okunamadı ({path}): {e}")

        if not records:
            return {"records": [], "vectorizer": None, "tfidf_matrix": None, "meta": {"indexed_records": 0}}

        texts = [r["_rag_text"] for r in records]
        vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(texts)
        logger.info(f"RAG geçici indeks: {len(records):,} kayıt (joblib yok, CSV fallback)")
        return {
            "version": 0,
            "records": records,
            "vectorizer": vectorizer,
            "tfidf_matrix": matrix,
            "meta": {
                "indexed_records": len(records),
                "source_stats": source_stats,
                "total_source_estimate": "CSV fallback (rag_index.joblib oluşturun: python build_rag_index.py)",
            },
        }

    @classmethod
    def reload_index(cls) -> None:
        """Bellek önbelleğini temizle — incremental RAG güncellemesi sonrası."""
        global _index_cache
        with _index_lock:
            _index_cache = None
        cls._load_index()

    @classmethod
    def get_index_info(cls) -> dict:
        idx = cls._load_index()
        meta = idx.get("meta", {})
        return {
            "indexed_records": meta.get("indexed_records", len(idx.get("records", []))),
            "source_stats": meta.get("source_stats", {}),
            "total_source_estimate": meta.get("total_source_estimate", ""),
            "index_path": _RAG_INDEX_PATH if os.path.isfile(_RAG_INDEX_PATH) else "CSV fallback",
            "loading": False,
        }

    # ------------------------------------------------------------------ #
    #  Arama
    # ------------------------------------------------------------------ #
    @classmethod
    def search(cls, query: str, top_k: int = _TOP_K) -> dict:
        idx = cls._load_index()
        records = idx.get("records", [])
        vectorizer = idx.get("vectorizer")
        matrix = idx.get("tfidf_matrix")
        meta = idx.get("meta", {})

        if not records or vectorizer is None or matrix is None:
            return {
                "matches": [],
                "match_count": 0,
                "indexed_records": 0,
                "source_summary": "Veri bulunamadı — python simulation/build_rag_index.py çalıştırın.",
                "context_text": "",
            }

        indexed = meta.get("indexed_records", len(records))
        q = query.lower().strip()

        try:
            query_vec = vectorizer.transform([q])
            sims = cosine_similarity(query_vec, matrix).flatten()
            top_indices = sims.argsort()[::-1][: top_k * 3]

            matches = []
            for i in top_indices:
                score = float(sims[i])
                if score < 0.001 and matches:
                    break
                rec = records[i]
                matches.append({**rec, "_score": score})
                if len(matches) >= top_k:
                    break

            # Benzerlik düşükse anahtar kelime / kategori fallback
            if not matches or (matches and matches[0]["_score"] < 0.05):
                matches = cls._keyword_fallback(records, q, top_k) or matches

            if not matches:
                matches = [{**records[i], "_score": 0.0} for i in range(min(top_k, len(records)))]

            context_lines = [
                f"- \"{m['_rag_text'][:200]}\" | {m['category']} | Puan: {m['rating']} | {m.get('sentiment', '')}"
                for m in matches
            ]
            source_stats = meta.get("source_stats", {})
            source_parts = [f"{k}: {v}" for k, v in source_stats.items()]
            source_summary = (
                f"{indexed:,} kayıtlı RAG indeksinden {len(matches)} benzer kayıt bulundu"
                + (f" ({'; '.join(source_parts[:3])})" if source_parts else "")
            )

            return {
                "matches": matches,
                "match_count": len(matches),
                "indexed_records": indexed,
                "source_summary": source_summary,
                "context_text": "\n".join(context_lines),
            }
        except Exception as e:
            logger.error(f"RAG arama hatası: {e}")
            return {
                "matches": [],
                "match_count": 0,
                "indexed_records": indexed,
                "source_summary": f"Arama hatası: {e}",
                "context_text": "",
            }

    @staticmethod
    def _keyword_fallback(records: list, query: str, top_k: int) -> list:
        keyword_map = [
            (("temizlik", "temiz", "kirli", "havlu", "banyo", "oda"), "Kat Hizmetleri"),
            (("yemek", "restoran", "buffet", "kahvaltı"), "Yiyecek"),
            (("klima", "wifi", "tv", "arıza", "teknik"), "Teknik"),
            (("havuz", "spa", "animasyon"), "Spa"),
            (("resepsiyon", "giriş", "check"), "Ön Büro"),
            (("fatura", "ücret", "depozito"), "Muhasebe"),
            (("personel", "kaba", "güler"), "Personel"),
        ]
        for keywords, cat_hint in keyword_map:
            if any(kw in query for kw in keywords):
                matched = [
                    r for r in records
                    if cat_hint.lower() in str(r.get("category", "")).lower()
                ]
                if matched:
                    return [{**r, "_score": 0.1} for r in matched[:top_k]]
        return []

    @staticmethod
    def get_rag_context(query: str) -> str:
        """Geriye dönük uyumluluk — context metni döndürür."""
        return RagService.search(query)["context_text"]

    # ------------------------------------------------------------------ #
    #  Yerel cevap üretici (Gemini gerekmez)
    # ------------------------------------------------------------------ #
    @classmethod
    def _build_local_answer(cls, query: str, search_result: dict) -> str:
        matches = search_result["matches"]
        indexed = search_result["indexed_records"]
        source_summary = search_result["source_summary"]

        if not matches:
            return (
                f"'{query}' için geçmiş yorumlarda doğrudan eşleşme bulunamadı. "
                f"Toplam {indexed:,} kayıtlı yorum arşivim var. "
                f"Daha spesifik bir soru sorabilirsiniz, örneğin 'temizlik şikayetleri' veya 'klima arızaları' gibi."
            )

        cat_counts: dict[str, int] = {}
        neg, pos, neu = 0, 0, 0
        total_rating = 0
        rating_count = 0
        for m in matches:
            cat = m.get("category", "Bilinmiyor")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            sent = str(m.get("sentiment", "")).upper()
            if "NEG" in sent:
                neg += 1
            elif "POS" in sent:
                pos += 1
            else:
                neu += 1
            try:
                total_rating += int(m.get("rating", 0))
                rating_count += 1
            except (ValueError, TypeError):
                logger.debug("_build_local_answer: hata yutuldu", exc_info=True)

        total = len(matches)
        top_cat = max(cat_counts, key=cat_counts.get)
        top_cat_count = cat_counts[top_cat]
        avg_rating = round(total_rating / rating_count, 1) if rating_count else "—"
        neg_pct = round(neg / total * 100) if total else 0
        pos_pct = round(pos / total * 100) if total else 0

        q = query.lower()
        sorted_cats = sorted(cat_counts.items(), key=lambda x: -x[1])

        lines = []
        lines.append(f"**{query}** hakkında {total} benzer yorum buldum.")

        if neg > pos:
            lines.append(f"Bunların %{neg_pct}'u olumsuz, %{pos_pct}'u olumlu. "
                        f"Ortalama puan {avg_rating}/5. Olumsuz geri bildirimler baskın.")
        elif pos > neg:
            lines.append(f"Bunların %{pos_pct}'u olumlu, %{neg_pct}'u olumsuz. "
                        f"Ortalama puan {avg_rating}/5. Genel memnuniyet iyi görünüyor.")
        else:
            lines.append(f"Ortalama puan {avg_rating}/5, karışık yorumlar mevcut.")

        if len(sorted_cats) > 0:
            cat_detail = ", ".join(f"{cat} ({cnt} yorum)" for cat, cnt in sorted_cats[:5])
            lines.append(f"Kategorilere göre dağılım: {cat_detail}.")

        if any(k in q for k in ("temizlik", "kirli", "oda", "havlu", "banyo")):
            lines.append(f"En çok {top_cat} kategorisinde şikayet var ({top_cat_count}/{total}). "
                        "Kat hizmetleri departmanına oda çıkış kontrol listesi güncellemesi önerilir.")
            if neg > 0:
                lines.append("Sık tekrarlanan sorunlar: temizlik standartlarının tutarsızlığı, "
                            "havlu değişiminin aksaması, banyo bakım eksiklikleri.")
        elif any(k in q for k in ("yemek", "restoran", "buffet", "kahvaltı", "akşam")):
            lines.append(f"En çok {top_cat} kategorisinde yorum var ({top_cat_count}/{total}). "
                        "Mutfak şefi ve F&B müdürüne servis hızı, yemek sıcaklığı ve "
                        "çeşitlilik denetimi önerilir.")
        elif any(k in q for k in ("klima", "wifi", "teknik", "arıza", "tv")):
            lines.append(f"{top_cat} öne çıkıyor ({top_cat_count}/{total}). "
                        "Teknik servise periyodik bakım ve 24 saat içinde müdahale "
                        "iş emri oluşturulması önerilir.")
        elif any(k in q for k in ("havuz", "spa", "hamam")):
            lines.append(f"{top_cat} en sık işlenen konu ({top_cat_count}/{total}). "
                        "Havuz hijyen ölçümlerinin sıklaştırılması ve spa ekibinin "
                        "bilgilendirilmesi önerilir.")
        elif any(k in q for k in ("personel", "garson", "resepsiyon", "çalışan")):
            lines.append(f"Personel ile ilgili yorumlar ağırlıklı olarak {top_cat} kategorisinde. "
                        "Eğer olumsuz geri bildirim varsa, ilgili departmanda ek eğitim planlanabilir.")
        elif any(k in q for k in ("fiyat", "ücret", "pahalı", "para")):
            lines.append(f"Fiyat-performans değerlendirmeleri çoğunlukla {top_cat} kategorisinde. "
                        "Rekabetçi fiyatlandırma için düzenli piyasa analizi önerilir.")
        elif any(k in q for k in ("genel", "memnuniyet", "memnun")):
            lines.append(f"Genel müşteri memnuniyetinde {top_cat} öne çıkıyor. "
                        f"%{pos_pct} olumlu, %{neg_pct} olumsuz geri bildirim var.")
        else:
            lines.append(f"Ağırlıklı kategori: {top_cat} ({top_cat_count}/{total} yorum). "
                        "Detaylı rapor için kategori bazında sorgulama yapabilirsiniz.")

        if neg > 0:
            lines.append(f"⚠ Olumsuz yorum oranı %{neg_pct} — trend takibi önerilir.")

        lines.append(f"\n📁 Kaynak: {source_summary} | Toplam indeks: {indexed:,} yorum")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Gemini (opsiyonel zenginleştirme)
    # ------------------------------------------------------------------ #
    @staticmethod
    async def call_gemini_api(prompt: str, api_key: str = None) -> str:
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "[Gemini API Key bulunamadı - Fallback]"

        async with gemini_semaphore:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent?key={api_key}"
            )
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            try:
                response = await asyncio.to_thread(
                    requests.post, url, json=payload,
                    headers={"Content-Type": "application/json"}, timeout=15,
                )
                if response.status_code == 200:
                    return response.json()["candidates"][0]["content"]["parts"][0]["text"]
                logger.error(f"Gemini API Hatası ({response.status_code}): {response.text[:300]}")
                return f"[API Hatası: {response.status_code}]"
            except Exception as e:
                logger.error(f"Gemini istek hatası: {e}")
                return "[İstek Zaman Aşımı/Bağlantı Hatası]"

    @staticmethod
    def _gemini_failed(response: str) -> bool:
        if not response or len(response.strip()) < 10:
            return True
        markers = ("[Gemini API Key", "[API Hatası", "[İstek Zaman Aşımı")
        if any(m in response for m in markers):
            return True
        empty_phrases = ("içim boş", "veri yok", "kayıt yok", "bağlam yok", "geçmiş kayıt bulunamad")
        return any(p in response.lower() for p in empty_phrases)

    @classmethod
    async def chat_with_rag(cls, query: str, api_key: str = None) -> dict:
        """
        Yerel RAG her zaman çalışır; Gemini varsa cevabı zenginleştirir.
        Çok alanlı yönlendirme: entity → domain/department → analytics → RAG.
        """
        from app.services.analytics_service import AnalyticsService
        from app.services.entity_tracker_service import get_entity_tracker_service
        from app.services.ontology_service import OntologyService

        entity_svc = get_entity_tracker_service()
        query_route = OntologyService.detect_query_type(query)

        entity_answer = entity_svc.format_entity_chat_answer(query)
        if entity_answer:
            entity = entity_svc.extract_entity(query)
            info = cls.get_index_info()
            report = None
            if entity:
                eid = entity.get("entity_id") or f"{entity.get('entity_type', '')}_{entity.get('entity_key', '')}"
                report = entity_svc.get_entity_report(eid)
            return {
                "response": entity_answer,
                "data_source": "entity_tracker + operasyon takip",
                "indexed_records": info.get("indexed_records", 0),
                "matches_found": 0,
                "mode": "entity_tracker",
                "query_route": query_route,
                "entity_type": entity["entity_type"] if entity else None,
                "entity_id": entity["entity_id"] if entity else None,
                "entity_report": report,
                "room_number": entity["entity_id"] if entity and entity["entity_type"] == "room" else None,
                "room_report": report if entity and entity["entity_type"] == "room" else None,
            }

        if query_route.get("type") == "domain":
            answer = cls._build_domain_answer(query, query_route["domain"], query_route["domain_label"])
            info = cls.get_index_info()
            return {
                "response": answer,
                "data_source": f"ontology + analytics ({query_route['domain']})",
                "indexed_records": info.get("indexed_records", 0),
                "matches_found": 0,
                "mode": "domain_analytics",
                "query_route": query_route,
            }

        if query_route.get("type") == "department":
            answer = cls._build_department_answer(query, query_route)
            info = cls.get_index_info()
            return {
                "response": answer,
                "data_source": f"ontology + analytics ({query_route.get('department_label', '')})",
                "indexed_records": info.get("indexed_records", 0),
                "matches_found": 0,
                "mode": "department_analytics",
                "query_route": query_route,
            }

        analytics_answer = AnalyticsService.chatbot_analytics_answer(query)
        if analytics_answer:
            info = cls.get_index_info()
            return {
                "response": analytics_answer,
                "data_source": "manager_review_store + analytics",
                "indexed_records": info.get("indexed_records", 0),
                "matches_found": 0,
                "mode": "analytics",
                "query_route": query_route,
            }

        search_result = cls.search(query)
        local_answer = cls._build_local_answer(query, search_result)

        effective_api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not effective_api_key:
            return {
                "response": local_answer,
                "data_source": search_result["source_summary"],
                "indexed_records": search_result["indexed_records"],
                "matches_found": search_result["match_count"],
                "mode": "local",
                "query_route": query_route,
            }


        context = search_result["context_text"]
        prompt = f"""Sen otel yöneticisine raporlayan bir Müşteri İlişkileri asistanısın.
Aşağıdaki {search_result['indexed_records']:,} kayıtlı RAG veritabanından bulunan geçmiş yorumları kullan.
Bağlamda veri vardır — "boş" veya "kayıt yok" deme. Türkçe, kısa ve profesyonel cevap ver.

BAĞLAM:
{context}

YÖNETİCİ SORUSU: {query}

CEVAP:"""

        gemini_response = await cls.call_gemini_api(prompt, effective_api_key)
        if cls._gemini_failed(gemini_response):
            return {
                "response": local_answer,
                "data_source": search_result["source_summary"] + " (Gemini kullanılamadı — yerel RAG)",
                "indexed_records": search_result["indexed_records"],
                "matches_found": search_result["match_count"],
                "mode": "local_fallback",
                "query_route": query_route,
            }

        footer = (
            f"\n\n---\n📊 Kaynak: {search_result['source_summary']} | "
            f"İndeks: {search_result['indexed_records']:,} kayıt"
        )
        return {
            "response": gemini_response.strip() + footer,
            "data_source": search_result["source_summary"],
            "indexed_records": search_result["indexed_records"],
            "matches_found": search_result["match_count"],
            "mode": "gemini",
            "query_route": query_route,
        }

    @classmethod
    def _build_domain_answer(cls, query: str, domain_id: str, domain_label: str) -> str:
        from app.services.ontology_service import OntologyService

        search_result = cls.search(query)
        dom = OntologyService.get_domain(domain_id)
        depts = dom.get("departments", []) if dom else []
        dept_names = ", ".join(d["label"] for d in depts[:6])

        lines = [
            f"📊 **{domain_label} — Alan Analizi**",
            "",
            f"**Soru:** {query}",
            f"**Tespit edilen alan:** {domain_label} (`{domain_id}`)",
            "",
        ]
        if dept_names:
            lines.append(f"**İlgili departmanlar:** {dept_names}")
            lines.append("")

        if search_result["matches"]:
            lines.append("**Benzer geçmiş kayıtlar:**")
            for i, m in enumerate(search_result["matches"][:3], 1):
                text = m["_rag_text"][:150] + ("..." if len(m["_rag_text"]) > 150 else "")
                lines.append(f"{i}. \"{text}\"")
            lines.append("")

        lines.append(
            f"💡 **Öneri:** {domain_label} alanındaki şikayetleri departman bazında "
            f"ayırmak için `/analyze-multidomain` endpoint'ini kullanın."
        )
        return "\n".join(lines)

    @classmethod
    def _build_department_answer(cls, query: str, route: dict) -> str:
        from app.services.ontology_service import OntologyService

        dept_label = route.get("department_label", "")
        domain_label = route.get("domain_label", "")
        path = OntologyService.get_department_path(route.get("domain", ""), route.get("department", ""))

        search_result = cls.search(query)
        lines = [
            f"🏢 **{path} — Departman Analizi**",
            "",
            f"**Soru:** {query}",
            f"**Alan:** {domain_label} | **Departman:** {dept_label}",
            "",
        ]

        if search_result["matches"]:
            neg = sum(1 for m in search_result["matches"] if "NEG" in str(m.get("sentiment", "")).upper())
            lines.append(f"**Benzer kayıt:** {search_result['match_count']} (olumsuz: {neg})")
            for i, m in enumerate(search_result["matches"][:3], 1):
                text = m["_rag_text"][:120] + ("..." if len(m["_rag_text"]) > 120 else "")
                lines.append(f"{i}. \"{text}\"")
            lines.append("")

        lines.append(
            f"💡 **Öneri:** {dept_label} birimine yönelik aspect detayları için "
            f"çok alanlı ABSA analizi çalıştırın."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Özet / öneri (analiz pipeline)
    # ------------------------------------------------------------------ #
    @staticmethod
    def generate_summary(text: str) -> str:
        if not text or not text.strip():
            return ""
        # Systemic summary: top operational complaints (not narrative opener)
        try:
            from app.services.clause_pipeline import ClausePipeline
            from app.services.absa_service import split_clauses_absa

            clauses = split_clauses_absa(text) or [text]
            decisions = ClausePipeline.process(clauses, full_text=text)
            built = ClausePipeline.summary(text, decisions=decisions)
            if built and built.strip():
                return built
        except Exception:
            logger.debug("generate_summary: hata yutuldu", exc_info=True)

        # Fallback: complaint-keyword sentence pick
        raw = re.sub(r"\s+", " ", text.strip())
        sentences = [s.strip() for s in re.split(r"[.!?]+", raw) if s.strip()]
        if not sentences:
            words = raw.split()
            return " ".join(words[:18]) + ("..." if len(words) > 18 else "")

        complaint_keywords = {
            "kötü", "kirli", "yavaş", "berbat", "pis", "rezalet", "arızalı", "klima", "banyo",
            "kuyruk", "sıra", "sira", "beklemek", "pişman", "pisman", "çöp", "cop", "yorucu",
            "yorgunluk", "düşük", "dusuk", "bulamad", "eksik", "kalitesiz", "karışık", "karisik",
            "temizletemed", "şikayet", "sikayet",
        }
        scored: list[tuple[int, str]] = []
        for s in sentences:
            low = s.lower()
            score = sum(1 for w in complaint_keywords if w in low)
            scored.append((score, s))
        scored.sort(key=lambda x: (-x[0], len(x[1])))
        best_score, best = scored[0]
        if best_score == 0:
            best = sentences[0]
        # Kısa şikayet özeti — uzun paragrafı kes
        words = best.split()
        if len(words) > 22:
            # Şikayet çekirdeğini bul (kuyruk/yorgunluk civarı)
            core_idx = next(
                (i for i, w in enumerate(words) if any(k in w.lower() for k in (
                    "kuyruk", "yorgun", "pişman", "pisman", "çöp", "cop", "berbat", "kirli",
                ))),
                0,
            )
            start = max(0, core_idx - 2)
            chunk = words[start:start + 20]
            best = " ".join(chunk).rstrip(",;:") + "..."
        elif not best.endswith((".", "…", "...")):
            best = best + "."
        return best

    @staticmethod
    def generate_suggestion(
        category: str,
        text: str,
        keywords: list[str],
        sentiment: str = "Neutral",
        is_mixed: bool = False,
        secondary_category: Optional[str] = None,
        is_humor: Optional[bool] = None,
        is_manipulation: Optional[bool] = None,
    ) -> str:
        from app.services.suggestion_engine import SuggestionContext, build_suggestion
        from app.services.turkish_nlp_utils import detect_humor, detect_manipulation

        ctx = SuggestionContext(
            category=category,
            text=text,
            keywords=keywords or [],
            sentiment=sentiment,
            is_mixed=is_mixed,
            secondary_category=secondary_category,
            is_humor=detect_humor(text) if is_humor is None else is_humor,
            is_manipulation=detect_manipulation(text) if is_manipulation is None else is_manipulation,
        )
        return build_suggestion(ctx)
