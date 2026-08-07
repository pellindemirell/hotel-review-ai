FROM python:3.10-slim

WORKDIR /app

# OCR için tesseract + Türkçe/İngilizce dil paketleri.
# ocr_service.py lang="tur+eng" istiyor; bunlar olmadan OCR sessizce atlanıyordu.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8000

# Ürün API'si app.main:app. Burada app.absa_platform.main:app vardı; o ayrı bir
# iç etiketleme aracı ve /analyze-review, /health, /translate, /ocr-image
# uçlarını sunmuyor — .NET entegrasyonu container'da her istekte 404 alıyordu.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
