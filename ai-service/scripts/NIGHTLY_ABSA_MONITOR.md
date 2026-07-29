# Nightly ABSA Monitor

Bu akış iki işi otomatikleştirir:

1. Uzun/noktalamasız mini eval setini büyütür.
2. Nightly kalite metriklerini üretir.

## Tek komut

PowerShell:

```powershell
cd D:\KodYazılımStaj1\ai-service
.\scripts\run_nightly_absa_monitor.ps1
```

## Üretilen çıktılar

- `D:\KodYazılımStaj1\audit_outputs\long_nopunct_eval_set.jsonl`
- `D:\KodYazılımStaj1\audit_outputs\long_nopunct_eval_set_summary.json`
- `D:\KodYazılımStaj1\audit_outputs\nightly_metrics\latest_metrics.json`
- `D:\KodYazılımStaj1\audit_outputs\nightly_metrics\latest_metrics.md`
- `D:\KodYazılımStaj1\audit_outputs\nightly_metrics\metrics_history.jsonl`

## İzlenen metrikler

- `genel_or_generic_clause_ratio`
- `avg_clause_per_review`
- `contrastive_negation_error_rate`
- `long_nopunct_undersegmented_rate`
- `long_nopunct_avg_clause_per_review`

## Windows Task Scheduler (02:30 gecelik)

```powershell
schtasks /Create /F /SC DAILY /ST 02:30 /TN "ABSA_Nightly_Monitor" /TR "powershell -ExecutionPolicy Bypass -File D:\KodYazılımStaj1\ai-service\scripts\run_nightly_absa_monitor.ps1"
```

## Elle dry-run

```powershell
cd D:\KodYazılımStaj1\ai-service
python .\scripts\build_long_nopunct_eval_set.py --add-count 50 --max-total 300
python .\scripts\nightly_absa_metrics.py --max-reviews 300
```
