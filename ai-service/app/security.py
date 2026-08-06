"""AI servisi için paylaşımlı anahtar (shared secret) tabanlı erişim denetimi.

Servis bugüne kadar tamamen korumasızdı: 64 ucun hiçbirinde kimlik doğrulama
yoktu ve bunların arasında `/retrain`, `/learning/bulk-train`, `/dashboard/seed`,
`PUT /hotel/profile`, `DELETE /test/reviews/{id}` gibi model eğiten ve veri
silen uçlar vardı. Servise ağdan erişebilen herkes modeli yeniden eğitebilir ve
veriyi silebilirdi.

Yaklaşım: **varsayılan kapalı**. Her istek anahtar ister; yalnızca aşağıdaki
allowlist'te olanlar serbesttir. Böylece sonradan eklenen bir uç, kimse
listeye dokunmayı unutsa bile otomatik olarak korumalı olur — tersi (varsayılan
açık + korunacakları tek tek işaretlemek) tam da bu servisin bugünkü hâli.

Anahtar `AI_SERVICE_API_KEY` ortam değişkeninden okunur ve istekte
`X-API-Key` başlığıyla ya da `Authorization: Bearer <anahtar>` ile gönderilir.
Anahtar tanımlı değilse korumalı uçlar 503 döner (fail-closed): yapılandırma
eksikken servisin sessizce herkese açık kalmasındansa kapalı kalması yeğdir.
"""

import hmac
import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("ai_service.security")

API_KEY = os.getenv("AI_SERVICE_API_KEY", "").strip()

# Anahtar istemeyen uçlar. Kısa tutulmalı: buraya eklenen her yol internete
# açıktır. Sağlık kontrolü .NET tarafının ayakta-mı sorgusu (AiAnalysisService
# .IsHealthyAsync), ontoloji uçları ise sabit meta veri döndürür.
PUBLIC_PATHS = frozenset({
    "/",
    "/health",
    "/health-status",
    # FastAPI'nin kendi dokümantasyon uçları (yalnızca şema, veri yok)
    "/docs",
    "/redoc",
    "/openapi.json",
})

PUBLIC_PREFIXES = ("/ontology",)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PREFIXES)


def _presented_key(request: Request) -> str:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return ""


async def api_key_middleware(request: Request, call_next):
    # CORS preflight'ı tarayıcı başlık ekleyemeden gönderir; engellenirse asıl
    # istek hiç yapılmaz ve hata "CORS hatası" gibi görünür.
    if request.method == "OPTIONS" or _is_public(request.url.path):
        return await call_next(request)

    if not API_KEY:
        logger.error(
            "AI_SERVICE_API_KEY tanımlı değil; korumalı uç reddedildi: %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "AI servisi yapılandırılmamış: AI_SERVICE_API_KEY "
                          "tanımlanmadan korumalı uçlar kullanılamaz."
            },
        )

    # compare_digest: sabit süreli karşılaştırma, anahtarın karakter karakter
    # tahmin edilmesini (timing attack) engeller.
    if not hmac.compare_digest(_presented_key(request), API_KEY):
        logger.warning(
            "Geçersiz API anahtarı: %s %s (istemci: %s)",
            request.method,
            request.url.path,
            request.client.host if request.client else "?",
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Geçersiz veya eksik API anahtarı."},
        )

    return await call_next(request)


def allowed_origins() -> list[str]:
    """CORS için izin verilen origin listesi.

    Önceden `allow_origins=["*"]` + `allow_credentials=True` ile açıktı; bu ikili
    zaten tarayıcı tarafında geçersiz bir kombinasyon ve herhangi bir sitenin
    servise istek atmasına izin veriyordu. Liste `AI_ALLOWED_ORIGINS` ile virgülle
    ayrılmış olarak verilir; verilmezse yerel geliştirme adresleri kullanılır.
    """
    raw = os.getenv("AI_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:4200",
            "http://127.0.0.1:4200",
            "http://localhost:5012",
            "http://127.0.0.1:5012",
        ]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
