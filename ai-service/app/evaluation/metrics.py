"""
HCOS Evaluation Framework — metrics for benchmarking each pipeline stage.
Handles both HODIP engine output format and gold annotation format.
"""

from __future__ import annotations

from typing import Any, Sequence


def accuracy(y_true: list[Any], y_pred: list[Any]) -> float:
    if not y_true:
        return 0.0
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


def precision_recall_f1(
    y_true: list[Any], y_pred: list[Any], positive_label: Any = None
) -> dict[str, float]:
    if not y_true:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if positive_label is not None:
        return _binary_metrics(y_true, y_pred, positive_label)
    labels = set(y_true) | set(y_pred)
    if not labels:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    precisions, recalls, f1s = [], [], []
    for label in labels:
        bp = _binary_metrics(y_true, y_pred, label)
        precisions.append(bp["precision"])
        recalls.append(bp["recall"])
        f1s.append(bp["f1"])
    return {
        "precision": sum(precisions) / len(precisions),
        "recall": sum(recalls) / len(recalls),
        "f1": sum(f1s) / len(f1s),
    }


def _binary_metrics(y_true, y_pred, positive_label):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == positive_label and p == positive_label)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != positive_label and p == positive_label)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == positive_label and p != positive_label)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def jaccard_similarity(set_true: set, set_pred: set) -> float:
    if not set_true and not set_pred:
        return 1.0
    if not set_true or not set_pred:
        return 0.0
    return len(set_true & set_pred) / len(set_true | set_pred)


def evaluate_pipeline(
    gold: list[dict],
    predictions: list[dict],
    task: str,
) -> dict[str, float]:
    if task == "clause_split":
        return _eval_clause_split(gold, predictions)
    elif task == "department":
        return _eval_department(gold, predictions)
    elif task == "failure_type":
        return _eval_failure_type(gold, predictions)
    elif task == "severity":
        return _eval_severity(gold, predictions)
    elif task == "root_cause":
        return _eval_root_cause(gold, predictions)
    else:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}


def _text_of(obj):
    """Extract text from either a string or dict with 'text' key."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("text", obj.get("clause", ""))
    return str(obj)


def _extract_gold_clauses(gold: dict) -> set[str]:
    clauses = gold.get("clauses", [])
    return {_text_of(c) for c in clauses}


def _extract_pred_clauses(pred: dict) -> set[str]:
    clauses = pred.get("clauses", [])
    return {_text_of(c) for c in clauses}


def _extract_gold_departments(gold: dict) -> list[str]:
    depts = gold.get("departments", [])
    return [d.get("department", "") if isinstance(d, dict) else str(d) for d in depts]


def _extract_pred_departments(pred: dict) -> list[str]:
    # HODIP puts dept info inside facts -> process_failures -> department
    depts = []
    for pf in pred.get("facts", {}).get("process_failures", []):
        if isinstance(pf, dict):
            d = pf.get("department", "")
            if d:
                depts.append(d)
    return depts


def _extract_gold_failure_types(gold: dict) -> list[str]:
    failures = gold.get("process_failures", [])
    return [f.get("failure_type", "") if isinstance(f, dict) else str(f) for f in failures]


def _extract_pred_failure_types(pred: dict) -> list[str]:
    failures = pred.get("facts", {}).get("process_failures", [])
    return [f.get("type", f.get("failure_type", "")) if isinstance(f, dict) else str(f) for f in failures]


def _extract_gold_severity(gold: dict) -> list:
    sev = gold.get("severity", [])
    if isinstance(sev, list):
        return [s.get("guest_impact", 0) if isinstance(s, dict) else s for s in sev]
    if isinstance(sev, dict):
        return [sev.get("guest_impact", 0)]
    return [sev]


def _extract_pred_severity(pred: dict) -> list:
    max_sev = pred.get("summary", {}).get("max_severity", "info")
    return [max_sev]


def _extract_gold_root_causes(gold: dict) -> list[str]:
    causes = gold.get("root_causes", [])
    return [c.get("cause_category", "") if isinstance(c, dict) else str(c) for c in causes]


def _extract_pred_root_causes(pred: dict) -> list[str]:
    causes = pred.get("facts", {}).get("root_causes", [])
    return [c.get("category", c.get("cause_category", "")) if isinstance(c, dict) else str(c) for c in causes]


def _eval_clause_split(gold, preds):
    scores = []
    for g, p in zip(gold, preds):
        g_clauses = _extract_gold_clauses(g)
        p_clauses = _extract_pred_clauses(p)
        scores.append(jaccard_similarity(g_clauses, p_clauses))
    acc = sum(scores) / len(scores) if scores else 0.0
    return {"accuracy": acc, "precision": 0.0, "recall": 0.0, "f1": 0.0}


def _eval_department(gold, preds):
    y_true, y_pred = [], []
    for g, p in zip(gold, preds):
        y_true.extend(_extract_gold_departments(g))
        y_pred.extend(_extract_pred_departments(p))
    if not y_true:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    prf = precision_recall_f1(y_true, y_pred)
    prf["accuracy"] = accuracy(y_true, y_pred)
    return prf


def _eval_failure_type(gold, preds):
    y_true, y_pred = [], []
    for g, p in zip(gold, preds):
        y_true.extend(_extract_gold_failure_types(g))
        y_pred.extend(_extract_pred_failure_types(p))
    if not y_true:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    prf = precision_recall_f1(y_true, y_pred)
    prf["accuracy"] = accuracy(y_true, y_pred)
    return prf


def _eval_severity(gold, preds):
    y_true, y_pred = [], []
    for g, p in zip(gold, preds):
        y_true.extend(_extract_gold_severity(g))
        y_pred.extend(_extract_pred_severity(p))
    if not y_true:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    prf = precision_recall_f1(y_true, y_pred)
    prf["accuracy"] = accuracy(y_true, y_pred)
    return prf


def _eval_root_cause(gold, preds):
    y_true, y_pred = [], []
    for g, p in zip(gold, preds):
        y_true.extend(_extract_gold_root_causes(g))
        y_pred.extend(_extract_pred_root_causes(p))
    if not y_true:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    prf = precision_recall_f1(y_true, y_pred)
    prf["accuracy"] = accuracy(y_true, y_pred)
    return prf
