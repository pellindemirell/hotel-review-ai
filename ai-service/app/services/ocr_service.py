import os
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

def perform_ocr(image_bytes: bytes, filename: str = "") -> tuple[str, float]:
    """
    Performs OCR text extraction on image bytes and computes a mock visual quality score.
    Has a fallback if pytesseract is not installed or configured.
    """
    ocr_text = ""
    quality_score = 0.90  # Default quality score
    
    # Save the bytes into a temporary PIL image
    import io
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        # Simple rule-based quality score based on dimensions
        # A tiny image has lower quality; high-res image has better quality
        pixels = width * height
        if pixels < 10000:  # < 100x100
            quality_score = 0.50
        elif pixels < 100000:  # < 300x300
            quality_score = 0.75
        else:
            quality_score = 0.95
            
        # Try to run pytesseract
        if pytesseract is not None:
            try:
                ocr_text = pytesseract.image_to_string(img, lang="tur+eng")
            except Exception as e:
                # If language files aren't found or engine not installed, fall back to default
                try:
                    ocr_text = pytesseract.image_to_string(img)
                except Exception:
                    ocr_text = ""
    except Exception as e:
        return f"Error reading image: {str(e)}", 0.0

    # Clean up ocr_text
    ocr_text = ocr_text.strip()
    
    # Fallback / mock response if OCR returned empty (e.g. no text or engine missing)
    if not ocr_text:
        # Mock OCR based on filename
        base_name = os.path.basename(filename).lower()
        if "fatura" in base_name or "receipt" in base_name:
            ocr_text = "MOCK OCR: Fatura veya fiş görseli algılandı. Ödeme tutarı: 1250 TL."
        elif "temizlik" in base_name or "dirty" in base_name:
            ocr_text = "MOCK OCR: Kirli oda veya banyo görseli algılandı."
        else:
            ocr_text = f"MOCK OCR: '{filename}' isimli görsel başarıyla yüklendi fakat üzerinde okunabilir metin bulunamadı."
            
    return ocr_text, quality_score
