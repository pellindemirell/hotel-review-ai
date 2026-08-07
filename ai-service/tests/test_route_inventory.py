"""Uç envanteri — sessizce kaybolan endpoint'lere karşı koruma.

Bu test neden var: `/translate` ucu bir dosya güncellemesi sırasında main.py
ile birlikte ezilip yok oldu. Servis sorunsuz açıldı, testler yeşildi, ama
.NET tarafı her çeviri isteğinde 404 aldı ve panelde "Türkçeye çevir" tuşu
sessizce çalışmaz oldu. Hatayı ancak kullanıcı fark etti.

Buradaki liste, .NET entegrasyonunun ve güvenlik katmanının bağlı olduğu
sözleşmedir. Bir uç kaybolursa test kırmızıya döner; kasıtlı kaldırılıyorsa
listeden de silinmesi gerekir — yani karar görünür olur.
"""
from __future__ import annotations

import pytest

from app.main import app
from app.security import PUBLIC_PATHS


def _routes() -> set[tuple[str, str]]:
    found = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or set()
        if path:
            for m in methods:
                found.add((m.upper(), path))
    return found


# .NET (AiAnalysisService) doğrudan bu uçları çağırıyor. Yolu ya da metodu
# değişirse entegrasyon kopar.
DOTNET_CONTRACT = [
    ("POST", "/analyze-review"),
    ("POST", "/translate"),
    ("POST", "/ocr-image"),
    ("GET", "/health"),
]


@pytest.mark.parametrize("method,path", DOTNET_CONTRACT)
def test_dotnet_contract_endpoints_exist(method: str, path: str) -> None:
    assert (method, path) in _routes(), (
        f"{method} {path} kayıp. .NET AiAnalysisService bu ucu çağırıyor; "
        "kaldırıldıysa C# tarafındaki çağrı da güncellenmeli."
    )


def test_health_is_public() -> None:
    """.NET worker'ı 'servis ayakta mı' sorgusunu anahtarsız yapıyor."""
    assert "/health" in PUBLIC_PATHS


def test_mutating_endpoints_are_not_public() -> None:
    """Model eğiten / veri silen uçlar asla anahtarsız erişilebilir olmamalı."""
    dangerous = {"/retrain", "/learning/bulk-train", "/dashboard/seed"}
    leaked = dangerous & set(PUBLIC_PATHS)
    assert not leaked, f"Bu uçlar korumasız kalmış: {sorted(leaked)}"


def test_route_count_does_not_silently_shrink() -> None:
    """Toplam uç sayısı için alt sınır.

    Kesin sayı değil alt sınır tutuluyor: yeni uç eklemek testi kırmamalı,
    ama toplu bir kayıp (dosyanın eski sürümle ezilmesi gibi) yakalanmalı.
    Bilinçli olarak uç kaldırıldıysa bu sayı da düşürülmeli.
    """
    paths = {p for _, p in _routes()}
    assert len(paths) >= 60, (
        f"Yalnızca {len(paths)} uç bulundu; toplu kayıp olabilir."
    )
