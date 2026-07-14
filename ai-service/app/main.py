from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import logging

from .db import get_db, engine, Base
from .services.sentiment_service import analyze_sentiment
from .services.category_service import classify_category
from .services.keyword_service import extract_keywords
from .services.ocr_service import perform_ocr

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title="HotelReviewAI AI Service",
    description="Python FastAPI service for Sentiment Analysis, Category Classification, Keyword Extraction, and OCR.",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request / Response Schemas
class ReviewAnalysisRequest(BaseModel):
    comment: str = Field(..., min_length=1, description="The review comment to analyze")
    rating: int = Field(..., ge=1, le=5, description="The review rating (1 to 5)")
    language: str = Field("tr", description="The language of the review")

class ReviewAnalysisResponse(BaseModel):
    sentiment: str = Field(..., description="Sentiment label (Positive, Negative, Neutral)")
    sentimentScore: float = Field(..., description="Sentiment score (-1.0 to 1.0)")
    category: str | None = Field(None, description="Classified category name")
    keywords: list[str] = Field(default_factory=list, description="Extracted keywords")
    summary: str = Field(..., description="Extracted summary of the review")
    suggestion: str = Field(..., description="Actionable suggestion for the department")
    confidence: float = Field(..., description="Confidence score of the analysis (0.0 to 1.0)")

class BatchAnalysisRequest(BaseModel):
    reviews: list[ReviewAnalysisRequest] = Field(..., description="List of reviews to analyze")

class BatchAnalysisResponse(BaseModel):
    analysis_results: list[ReviewAnalysisResponse]

class OCRResponse(BaseModel):
    ocr_text: str = Field(..., description="Extracted text from image")
    quality_score: float = Field(..., description="Visual quality score (0.0 to 1.0)")

# Ensure tables are created if needed (in case migrations are not run yet)
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified.")
except Exception as e:
    logger.warning(f"Could not automatically create/verify tables: {e}")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/analyze-review", response_model=ReviewAnalysisResponse)
def analyze_review_endpoint(request: ReviewAnalysisRequest, db: Session = Depends(get_db)):
    """
    Analyzes a single review to extract sentiment, category classification, keywords,
    summary and actionable suggestion.
    """
    try:
        # 1. Sentiment analysis
        sentiment_enum, sentiment_score = analyze_sentiment(request.comment, request.rating)
        sentiment_map = {0: "Positive", 1: "Negative", 2: "Neutral"}
        sentiment_label = sentiment_map.get(sentiment_enum, "Neutral")
        
        # 2. Category classification
        category_id, category_name = classify_category(request.comment, db)
        
        # 3. Keyword extraction
        keywords = extract_keywords(request.comment)
        
        # 4. Generate summary
        comment_words = request.comment.split()
        if len(comment_words) <= 8:
            summary = request.comment
        else:
            summary = " ".join(comment_words[:8]) + "..."
            
        # 5. Generate action suggestion
        suggestion = ""
        if sentiment_label == "Negative":
            if category_name == "Temizlik":
                suggestion = "Housekeeping departmanı ilgili alanın temizlik kontrol listelerini güncellemeli ve personeli uyarmalıdır."
            elif category_name == "Yemek":
                suggestion = "F&B departmanı şikayete konu olan yemek/içecek kalitesini ve sunum standartlarını gözden geçirmelidir."
            elif category_name == "Personel":
                suggestion = "İlgili departman yöneticisi personel eğitimi ve müşteri ilişkileri standartlarını gözden geçirmelidir."
            elif category_name == "Oda":
                suggestion = "Teknik Servis ve Kat Hizmetleri oda donanımını ve bakım durumunu kontrol etmelidir."
            else:
                suggestion = "Şikayet konusu detaylı incelenerek ilgili departmana aksiyon atanmalıdır."
        elif sentiment_label == "Positive":
            suggestion = "Misafire olumlu geri bildirimi için teşekkür edilmeli ve sunulan hizmet standardı korunmalıdır."
        else:
            suggestion = "Misafir geri bildirimi hizmet kalitesini artırmak için takip edilmeli, gerekirse ek bilgi alınmalıdır."
            
        # 6. Confidence calculation
        # Simple rule: higher confidence if rating matches sentiment, slightly lower if keywords conflict
        confidence = 0.85
        if (request.rating >= 4 and sentiment_label == "Negative") or (request.rating <= 2 and sentiment_label == "Positive"):
            confidence = 0.60
            
        response = ReviewAnalysisResponse(
            sentiment=sentiment_label,
            sentimentScore=sentiment_score,
            category=category_name,
            keywords=keywords,
            summary=summary,
            suggestion=suggestion,
            confidence=confidence
        )
        return response
        
    except Exception as e:
        logger.error(f"Error in review analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal analysis error: {str(e)}")


@app.post("/analyze-batch", response_model=BatchAnalysisResponse)
def analyze_batch_endpoint(request: BatchAnalysisRequest, db: Session = Depends(get_db)):
    """
    Analyzes multiple reviews in a single batch request.
    """
    results = []
    for item in request.reviews:
        try:
            # Re-use analysis logic
            sentiment_enum, sentiment_score = analyze_sentiment(item.comment, item.rating)
            sentiment_map = {0: "Positive", 1: "Negative", 2: "Neutral"}
            sentiment_label = sentiment_map.get(sentiment_enum, "Neutral")
            
            _, category_name = classify_category(item.comment, db)
            keywords = extract_keywords(item.comment)
            
            comment_words = item.comment.split()
            summary = item.comment if len(comment_words) <= 8 else " ".join(comment_words[:8]) + "..."
            
            suggestion = "Misafir geri bildirimi hizmet kalitesini artırmak için takip edilmelidir."
            if sentiment_label == "Negative":
                suggestion = f"{category_name or 'İlgili'} departmanı şikayet konusunu detaylıca incelemeli ve aksiyon almalıdır."
            elif sentiment_label == "Positive":
                suggestion = "Hizmet standardı korunmalıdır."
                
            results.append(ReviewAnalysisResponse(
                sentiment=sentiment_label,
                sentimentScore=sentiment_score,
                category=category_name,
                keywords=keywords,
                summary=summary,
                suggestion=suggestion,
                confidence=0.80
            ))
        except Exception as e:
            logger.error(f"Batch item failed: {e}")
            # Append empty analysis instead of failing whole batch
            results.append(ReviewAnalysisResponse(
                sentiment="Neutral",
                sentimentScore=0.0,
                category=None,
                keywords=[],
                summary="Analysis failed",
                suggestion="No suggestion",
                confidence=0.0
            ))
            
    return BatchAnalysisResponse(analysis_results=results)


@app.post("/ocr-image", response_model=OCRResponse)
async def ocr_image_endpoint(file: UploadFile = File(...)):
    """
    Extracts text from uploaded image file.
    """
    try:
        content = await file.read()
        ocr_text, quality_score = perform_ocr(content, file.filename)
        return OCRResponse(ocr_text=ocr_text, quality_score=quality_score)
    except Exception as e:
        logger.error(f"Error in OCR endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OCR processing error: {str(e)}")
