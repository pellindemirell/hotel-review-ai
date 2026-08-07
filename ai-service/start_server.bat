@echo off
title HCOS Review Platform
cd /d D:\KodYazılımStaj1\ai-service
set PYTHONPATH=D:\KodYazılımStaj1\ai-service

echo ========================================
echo   HCOS ABSA Review Platform v2
echo ========================================
echo.
echo  Yerel:  http://localhost:8000
echo  Ag:     http://%COMPUTERNAME%:8000
echo.
echo  Admin:  http://localhost:8000/admin
echo.
echo  Token'lar: arda1, arda2, pelin, bahriye, huseyin, ozgur
echo  Admin:     admin123
echo.
echo  Baslatiliyor...
echo.

python -m uvicorn app.absa_platform.main:app --host 0.0.0.0 --port 8000
pause
