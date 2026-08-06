$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\KodYazılımStaj1\ai-service"
Set-Location $ProjectRoot

Write-Host "== ABSA Nightly Monitor Start ==" -ForegroundColor Cyan

# 1) Expand long/no-punctuation mini eval set
python .\scripts\build_long_nopunct_eval_set.py `
  --add-count 200 `
  --max-total 1200

# 2) Generate nightly ABSA quality metrics
python .\scripts\nightly_absa_metrics.py

Write-Host "== ABSA Nightly Monitor Done ==" -ForegroundColor Green
