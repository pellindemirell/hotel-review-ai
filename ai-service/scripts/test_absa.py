import sys
sys.path.insert(0, ".")
from app.absa_platform.absa_engine import analyze_batch

text = "Bugun otelden ayrildim ve tek kelimeyle ozetleyecek olsaydim sadece yorgunluk diyebilirdim inanilmaz kuyruklar inanilmaz siralar beklemek zorunda kaldik. Odalar cok kucuk yemeklerin lezzeti ortalamaydi ama kiyma kalitesi cok dusuktu. A la carte olarak italyan restoran basariliydi. Eray Beye tesekkur ederiz. Personel cabalari genel olarak iyiydi."

result = analyze_batch(text)
for c in result["clauses"]:
    print(f"{c['priority']:6s} {c['sentiment']:6s} ({c['sentiment_score']:5.2f}) {c['aspect']:12s} {c['department']:20s} | {c['text'][:60]}")
print(f"\nSummary: {result}")
