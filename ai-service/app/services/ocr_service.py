import cv2
import numpy as np
import logging

try:
    import pytesseract
except ImportError:
    pytesseract = None

logger = logging.getLogger("ai_service")

# Laplacian varyansı bu eşiğin altındaysa görsel bulanık kabul edilir
QUALITY_ACCEPT_THRESHOLD = 0.45


class OcrService:
    @staticmethod
    def process_image(image_bytes: bytes) -> dict:
        """
        Görseli işler: OpenCV ile netlik skoru hesaplar, opsiyonel Tesseract OCR uygular.
        Tesseract kurulu değilse ocr_text boş döner (graceful fallback).
        """
        ocr_text = ""
        image_quality_score = 0.0
        is_acceptable = False

        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                logger.error("Görsel yüklenemedi veya bozuk formatta.")
                return {
                    "ocr_text": "",
                    "quality_score": 0.0,
                }

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            image_quality_score = round(min(1.0, max(0.0, laplacian_var / 300.0)), 2)
            is_acceptable = image_quality_score >= QUALITY_ACCEPT_THRESHOLD

            if pytesseract:
                import os
                import shutil
                if not shutil.which("tesseract"):
                    env_path = os.getenv("TESSERACT_CMD") or os.getenv("TESSERACT_PATH")
                    if env_path and os.path.exists(env_path):
                        pytesseract.pytesseract.tesseract_cmd = env_path
                    else:
                        common_paths = [
                            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
                        ]
                        for path in common_paths:
                            if os.path.exists(path):
                                pytesseract.pytesseract.tesseract_cmd = path
                                break
                try:
                    ocr_text = pytesseract.image_to_string(img, lang="tur+eng").strip()
                except Exception as e:
                    logger.warning(
                        "Tesseract OCR kullanılamadı (%s); ocr_text boş döndürülüyor.",
                        e,
                    )
            else:
                logger.info("pytesseract yüklü değil; OCR atlandı.")

        except Exception as e:
            logger.error(f"Görsel işlenirken beklenmedik hata oluştu: {e}")
            return {
                "ocr_text": "",
                "quality_score": 0.0,
            }

        return {
            "ocr_text": ocr_text,
            "quality_score": image_quality_score,
        }
