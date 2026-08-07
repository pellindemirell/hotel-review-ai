#!/bin/bash
# Hotel ABSA AI Service macOS / Linux Startup Script

echo "============================================================"
echo "      Otel Restoran Akıllı ABSA AI Servisi Başlatılıyor"
echo "============================================================"

# Environment variables
export PYTHONUNBUFFERED=1
export PORT=${PORT:-8000}
export HOST=${HOST:-"0.0.0.0"}

# Python execution check
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "Hata: Python ortamda bulunamadı! Lütfen Python 3.9+ yükleyin."
    exit 1
fi

echo "Python Komutu: $PYTHON_CMD"
echo "Servis Adresi: http://$HOST:$PORT"
echo "API Dokümantasyonu: http://localhost:$PORT/docs"
echo "============================================================"

$PYTHON_CMD -m uvicorn app.main:app --host $HOST --port $PORT --reload
