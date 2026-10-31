"""Dependence-aware helpers and the predeclared three-test family."""
from __future__ import annotations

from pathlib import Path
import json
import numpy as np
from scipy import stats as scipy_stats


def adjust_pvalues(pvalues, method="holm"):
    """Adjust a complete family; missing tests conservatively occupy a p=1 slot."""
    values = np.asarray([1.0 if p is None or not np.isfinite(p) else p for p in pvalues], float)
    if np.any((values < 0) | (values > 1)):
        raise ValueError("p-values must lie in [0,1]")
    order = np.argsort(values, kind="stable")
    n = len(values)
    if method == "holm":
        ranked = np.maximum.accumulate(values[order] * (n - np.arange(n)))
    elif method == "bh":
        ranked = np.minimum.accumulate((values[order] * n / (np.arange(n) + 1))[::-1])[::-1]
    else:
        raise ValueError(method)
    out = np.empty(n)
    out[order] = np.minimum(ranked, 1)
    return [None if p is None or not np.isfinite(p) else float(a) for p, a in zip(pvalues, out)]


def cluster_ols(x, y, groups):
    """OLS with CR1 whole-series sandwich covariance and t(G-1) tests."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    labels, inverse = np.unique(np.asarray(groups, str), return_inverse=True)
    n, p = x.shape
    if len(labels) < 3 or n <= p or np.linalg.matrix_rank(x) != p:
        raise ValueError("insufficient independent series or rank-deficient design")
    bread = np.linalg.inv(x.T @ x)
    beta = bread @ x.T @ y
    residual = y - x @ beta
    scores = np.zeros((len(labels), p))
    np.add.at(scores, inverse, x * residual[:, None])
    covariance = bread @ scores.T @ scores @ bread
    covariance *= len(labels) / (len(labels) - 1) * (n - 1) / (n - p)
    se = np.sqrt(np.maximum(0, np.diag(covariance)))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = beta / se
    pvalues = 2 * scipy_stats.t.sf(np.abs(t), len(labels) - 1)
    pvalues[(se == 0) & (beta == 0)] = 1
    return {"beta": beta, "se": se, "p": pvalues, "n_series": len(labels)}


def bootstrap_ols(x, y, groups, coefficient, n_bootstrap=2000, seed=42):
    """Resample complete series by multiplying their sufficient statistics."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    labels, inverse = np.unique(np.asarray(groups, str), return_inverse=True)
    xx = np.zeros((len(labels), x.shape[1], x.shape[1]))
    xy = np.zeros((len(labels), x.shape[1]))
    order = np.argsort(inverse, kind="stable")
    starts = np.r_[0, np.flatnonzero(np.diff(inverse[order])) + 1, len(order)]
    for i, (start, stop) in enumerate(zip(starts[:-1], starts[1:])):
        block = order[start:stop]
        xx[i] = x[block].T @ x[block]
        xy[i] = x[block].T @ y[block]
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n_bootstrap):
        counts = rng.multinomial(len(labels), np.full(len(labels), 1 / len(labels)))
        lhs = np.einsum("g,gij->ij", counts, xx)
        rhs = np.einsum("g,gi->i", counts, xy)
        if np.linalg.matrix_rank(lhs) == lhs.shape[0]:
            values.append(float(np.linalg.solve(lhs, rhs)[coefficient]))
    return {"ci_low": float(np.quantile(values, .025)) if values else None,
            "ci_high": float(np.quantile(values, .975)) if values else None,
            "successful_replicates": len(values), "requested_replicates": n_bootstrap}


def update_confirmatory_family(output):
    """Holm across RQ1/RQ3/RQ4, separately for val and frozen test.

    A missing or infeasible test keeps its family slot; it cannot make the
    remaining tests easier to reject. Multiple conflicting primary records
    invalidate that slot rather than selecting the smallest p-value.
    """
    from .common import atomic_json
    from datetime import datetime, timezone
    output = Path(output)
    candidates = {}
    for path in sorted((output / "results").glob("*.json")):
        if path.name == "confirmatory.json":
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for row in payload if isinstance(payload, list) else [payload]:
            if not isinstance(row, dict) or row.get("is_baseline"):
                continue
            details = row.get("details", {})
            # Dashboard envelopes may keep structured details in notes.
            if not isinstance(details, dict):
                continue
            c = details.get("confirmatory")
            if isinstance(c, dict):
                key = (c.get("split", row.get("split")), c.get("rq", c.get("id")))
                candidates.setdefault(key, []).append(c)
    rows = []
    for split in ("val", "test"):
        raw, records = [], []
        for rq in ("RQ1", "RQ3", "RQ4"):
            found = candidates.get((split, rq), [])
            valid = len(found) == 1 and found[0].get("p_value") is not None
            p = float(found[0]["p_value"]) if valid else None
            if p is not None and (not np.isfinite(p) or not 0 <= p <= 1):
                p = None
            raw.append(p)
            records.append({"rq": rq, "p_value": p,
                            "status": "estimated" if p is not None else "missing_or_conflicting"})
        adjusted = adjust_pvalues(raw, "holm")
        for record, p in zip(records, adjusted):
            record.update(p_holm=p, reject_005=bool(p is not None and p <= .05))
        metrics = {f"{r['rq']}_p_holm": r["p_holm"] for r in records if r["p_holm"] is not None}
        metrics["family_size"] = 3
        rows.append({"method": "Predeclared three-test Holm family", "task": "confirmation",
                     "split": split, "is_baseline": False, "metrics": metrics,
                     "lower_is_better": [k for k in metrics if k.endswith("p_holm")],
                     "notes": "RQ1 grammar, RQ3 late-by-score coverage, RQ4 persistence. Missing tests retain family slots.",
                     "details": {"tests": records}, "updated": datetime.now(timezone.utc).isoformat()})
    atomic_json(output / "results" / "confirmatory.json", rows)
    update_exploratory_family(output)
    return rows


def update_exploratory_family(output):
    """One declared BH family across all reported motif and secondary tests.

    Includes both vocabularies, both held-out splits when evaluated, and all
    nonconfirmatory pressure responses. It does not reuse the per-vocabulary
    diagnostic q-values as corrected scientific claims.
    """
    from .common import atomic_json, now
    output = Path(output)
    records = []
    for path in sorted((output / "results").glob("*.json")):
        if not (path.name.startswith("tokens_learned_") or path.name.startswith("tokens_handcrafted_")
                or path.name == "pressure.json"):
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for row in payload if isinstance(payload, list) else [payload]:
            details = row.get("details", {})
            for motif in details.get("motifs", []):
                p = motif.get("p_value")
                if p is not None and np.isfinite(p):
                    records.append({"id": path.stem + ":motif:" + ",".join(map(str, motif["motif"])),
                                    "source": path.name, "split": row.get("split"), "kind": "motif",
                                    "motif": motif["motif"], "p_value": float(p)})
            for response, model in details.get("models", {}).items():
                if response == "uncovered":
                    continue
                p = model.get("p_value")
                if p is not None and np.isfinite(p):
                    records.append({"id": f"pressure:{row.get('split')}:{response}", "source": path.name,
                                    "split": row.get("split"), "kind": "pressure_secondary",
                                    "response": response, "p_value": float(p)})
    for row, q in zip(records, adjust_pvalues([r["p_value"] for r in records], "bh")):
        row["q_value"] = q
        row["reject_005"] = bool(q <= .05)
    payload = {"method": "Pooled exploratory BH", "task": "exploratory_multiplicity", "split": "all",
               "is_baseline": False, "metrics": {"tests": len(records), "discoveries_q005": sum(r["reject_005"] for r in records)},
               "details": {"tests": records, "family": "All available learned/control motif tests across evaluated val/test plus all secondary pressure responses in current result files"},
               "notes": "The pooled q_value is the reported exploratory correction; per-vocabulary q-values are diagnostics only. No exploratory finding is confirmatory.",
               "updated": now()}
    atomic_json(output / "results" / "exploratory.json", payload)
    return payload
