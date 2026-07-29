FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright sistem bağımlılıkları + Chromium tarayıcısını indir
RUN playwright install-deps chromium && \
    playwright install chromium

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.absa_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]
