"""Overnight ABSA boost loop until morning deadline.

Runs: accuracy benchmark -> regression tests -> optional gold-only retrain
Writes continuous reports under audit_outputs/.
Uses unbuffered prints and a fast accuracy probe to avoid silent hangs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(r"D:\KodYazılımStaj1")
AI = ROOT / "ai-service"
OUT = ROOT / "audit_outputs"
OUT.mkdir(parents=True, exist_ok=True)

DEADLINE_LOCAL = datetime(2026, 7, 29, 8, 0, 0)


def now_local() -> datetime:
    return datetime.now()


def run(cmd: list[str], cwd: Path, timeout: int = 900) -> dict:
    started = time.time()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        return {
            "cmd": " ".join(cmd),
            "returncode": p.returncode,
            "elapsed_sec": round(time.time() - started, 2),
            "stdout_tail": (p.stdout or "")[-4000:],
            "stderr_tail": (p.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired as e:
        out = ""
        try:
            out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        except Exception:
            out = ""
        return {
            "cmd": " ".join(cmd),
            "returncode": -1,
            "elapsed_sec": round(time.time() - started, 2),
            "stdout_tail": (out or str(e))[-1000:],
            "stderr_tail": "TIMEOUT",
        }


def parse_accuracy(stdout: str) -> dict:
    out = {"dept_acc": None, "sent_acc": None, "n": None, "fails": None}
    for line in stdout.splitlines():
        low = line.lower()
        if low.startswith("dept ") and "/" in line and "%" in line:
            try:
                left, pct = line.split("=", 1)
                nums = left.split()[1]
                _ok, n = nums.split("/")
                out["dept_acc"] = float(pct.strip().replace("%", ""))
                out["n"] = int(n)
            except Exception:
                pass
        if low.startswith("sent ") and "/" in line and "%" in line:
            try:
                pct = line.split("=")[1].strip().replace("%", "")
                out["sent_acc"] = float(pct)
            except Exception:
                pass
        if low.startswith("fails "):
            try:
                out["fails"] = int(line.split()[1])
            except Exception:
                pass
        if "departman" in low and "%" in line:
            try:
                pct = line.split("%")[0].split()[-1].replace(",", ".")
                out["dept_acc"] = float(pct)
            except Exception:
                pass
        if "duygu" in low and "%" in line:
            try:
                pct = line.split("%")[0].split()[-1].replace(",", ".")
                out["sent_acc"] = float(pct)
            except Exception:
                pass
    return out


FAST_PROBE = r"""
import os,sys,json
from pathlib import Path
from datetime import datetime
sys.path.insert(0,r'D:\KodYazılımStaj1\ai-service')
os.chdir(r'D:\KodYazılımStaj1')
from simulation.test_absa_department_accuracy import LABELED_CLAUSES,_dept_match,_sent_match
from app.services.absa_service import AbsaService
from app.services.ontology_service import reload_ontology
reload_ontology()
print('start',len(LABELED_CLAUSES), flush=True)
dc=sc=0; fails=[]
for i,(text,exp_d,exp_s) in enumerate(LABELED_CLAUSES,1):
    r=AbsaService.analyze_multidomain(text)
    pred_d=r.aspects[0].department_label if r.aspects else ''
    pred_s=r.aspects[0].sentiment if r.aspects else ''
    okd=_dept_match(pred_d,exp_d); oks=_sent_match(pred_s,exp_s)
    dc+=okd; sc+=oks
    if not okd: fails.append((text[:80],exp_d,pred_d))
    if i%50==0: print('progress',i, flush=True)
n=len(LABELED_CLAUSES)
print(f'DEPT {dc}/{n}={100*dc/n:.1f}%', flush=True)
print(f'SENT {sc}/{n}={100*sc/n:.1f}%', flush=True)
print('FAILS',len(fails), flush=True)
for f in fails: print(' -',f, flush=True)
Path(r'D:\KodYazılımStaj1\audit_outputs\overnight_accuracy_metrics.json').write_text(
    json.dumps({
        'dept_acc': round(100*dc/n,2),
        'sent_acc': round(100*sc/n,2),
        'n': n,
        'fails': len(fails),
        'fail_samples': fails,
        'updated_at': datetime.now().isoformat(),
        'target_met': (100*dc/n)>=95 and (100*sc/n)>=90,
        'source': 'overnight_fast_probe',
    }, ensure_ascii=False, indent=2),
    encoding='utf-8',
)
"""


def main() -> None:
    history = []
    iter_n = 0
    print(f"[overnight] start {now_local().isoformat()} deadline={DEADLINE_LOCAL.isoformat()}", flush=True)

    while now_local() < DEADLINE_LOCAL:
        iter_n += 1
        print(f"\n[overnight] === ITER {iter_n} @ {now_local().isoformat()} ===", flush=True)
        entry = {"iter": iter_n, "started_at": now_local().isoformat(), "steps": {}}

        acc = run([sys.executable, "-u", "-c", FAST_PROBE], ROOT, timeout=1200)
        entry["steps"]["accuracy"] = {**acc, "parsed": parse_accuracy(acc.get("stdout_tail", ""))}
        print(
            f"[overnight] accuracy rc={acc['returncode']} "
            f"parsed={entry['steps']['accuracy']['parsed']} elapsed={acc['elapsed_sec']}",
            flush=True,
        )

        tests = [
            "tests/test_absa_contrastive_split_fallback_regression.py",
            "tests/test_mixed_turkish_hotel_absa_fix.py",
            "tests/test_user_paste_absa_regression.py",
            "tests/test_user_reported_regression.py",
            "tests/test_batch_audit_regression.py",
            "tests/test_bayram_cockroach_review.py",
            "tests/test_berbat_otel_staff_parking_review.py",
            "tests/test_crystal_family_positive_review.py",
            "tests/test_overnight_edge_cases.py",
        ]
        reg = run([sys.executable, "-u", "-m", "pytest", *tests, "-q", "--tb=line"], AI, timeout=1800)
        entry["steps"]["regression"] = reg
        print(f"[overnight] regression rc={reg['returncode']} elapsed={reg['elapsed_sec']}", flush=True)

        if now_local() < DEADLINE_LOCAL:
            hold = run(
                [sys.executable, "-u", str(ROOT / "simulation" / "evaluate_category_holdout.py"), "--skip-absa"],
                ROOT,
                timeout=300,
            )
            entry["steps"]["category_holdout"] = hold
            print(f"[overnight] holdout rc={hold['returncode']} elapsed={hold['elapsed_sec']}", flush=True)

        if iter_n % 2 == 0 and now_local() < DEADLINE_LOCAL:
            tr = run([sys.executable, "-u", str(ROOT / "simulation" / "gold_only_retrain.py")], ROOT, timeout=1200)
            entry["steps"]["retrain"] = tr
            print(f"[overnight] retrain rc={tr['returncode']} elapsed={tr['elapsed_sec']}", flush=True)

        history.append(entry)
        (OUT / "overnight_loop_history.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        latest = {
            "updated_at": now_local().isoformat(),
            "iter": iter_n,
            "deadline": DEADLINE_LOCAL.isoformat(),
            "last": entry,
            "target": {"dept_acc": 95.0, "sent_acc": 90.0},
            "parsed_accuracy": entry["steps"]["accuracy"].get("parsed"),
        }
        metrics_path = OUT / "overnight_accuracy_metrics.json"
        try:
            prev = json.loads(metrics_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and "dept_acc" in prev:
                for k in ("dept_acc", "sent_acc", "n", "fails", "fail_samples", "target_met", "source"):
                    if k in prev:
                        latest[k] = prev[k]
        except Exception:
            pass
        metrics_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(20)

    report = [
        "# Overnight Final Report",
        "",
        f"- Finished: `{now_local().isoformat()}`",
        f"- Iterations: `{iter_n}`",
        f"- Deadline: `{DEADLINE_LOCAL.isoformat()}`",
        "",
        "## Last metrics",
        "```json",
        json.dumps(history[-1] if history else {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Backend delivery package",
        "- `ai-service/` (ABSA pipeline + rules)",
        "- `ai-service/config/absa/clause_pipeline.yaml`",
        "- `simulation/category_model.joblib`",
        "- `simulation/vectorizer.joblib`",
        "- `simulation/clause_split_model.joblib`",
        "- `simulation/berturk_clause_model/` (optional fallback)",
        "",
        "## Notes",
        "- Bu döngü fast probe + regression + holdout + periyodik gold-only retrain çalıştırır.",
        "- Hata çıktıları `overnight_loop_history.json` içinde tutulur.",
    ]
    (OUT / "overnight_final_report.md").write_text("\n".join(report), encoding="utf-8")
    print("[overnight] DONE", flush=True)


if __name__ == "__main__":
    main()
