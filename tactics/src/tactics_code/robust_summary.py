"""Summarize isolated P4 runs; never run extraction, inference, or model fitting.

The output is written only on explicit invocation. Each variant retains a
three-test Holm family, including missing/ineligible tests. Raw descriptive
p-values are separate from provenance/vocabulary-gated confirmatory p-values.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .common import atomic_json


RQS = ("RQ1", "RQ3", "RQ4")


def mapping(value):
    return value if isinstance(value, dict) else {}


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def pvalue(value):
    number = finite(value)
    return number if number is not None and 0 <= number <= 1 else None


def read(path, warnings):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        warnings.append(f"{path.name}: {type(exc).__name__}: {exc}")
        return None


def rows(payload):
    values = payload if isinstance(payload, list) else [payload]
    return [value for value in values if isinstance(value, dict)]


def choose(payload, split, warnings, source, allow_all=False):
    matches = [row for row in rows(payload)
               if not row.get("is_baseline")
               and row.get("split") in ({split, "all", None} if allow_all else {split})]
    if len(matches) > 1:
        warnings.append(f"{source}: conflicting primary records for {split}; omitted")
        return {}
    return matches[0] if matches else {}


def interval(model):
    """Never mix the OLS sensitivity interval with a MixedLM estimate."""
    low, high = finite(model.get("ci_low")), finite(model.get("ci_high"))
    method = "reported model interval"
    if low is None or high is None:
        bootstrap = mapping(model.get("series_bootstrap"))
        low, high = finite(bootstrap.get("ci_low")), finite(bootstrap.get("ci_high"))
        method = "whole-series bootstrap"
    if low is None or high is None:
        ci = model.get("ci95")
        if isinstance(ci, (list, tuple)) and len(ci) == 2:
            low, high = finite(ci[0]), finite(ci[1])
            method = "whole-series bootstrap"
    if low is None or high is None or low > high:
        return {"ci_low": None, "ci_high": None, "ci_method": None}
    return {"ci_low": low, "ci_high": high, "ci_method": method}


def pressure_effect(model):
    model = mapping(model)
    return {"status": model.get("status", "missing"),
            "estimate": finite(model.get("estimate")), **interval(model),
            "p_value": pvalue(model.get("p_value")), "method": model.get("method"),
            "n_series": model.get("n_series"), "reason": model.get("reason")}


def holm(candidates, split):
    """Missing/conflicting tests occupy p=1 slots but remain null in output."""
    tests = []
    for rq in RQS:
        found = candidates.get((split, rq), [])
        p = pvalue(found[0].get("p_value")) if len(found) == 1 else None
        status = ("estimated" if p is not None else
                  "conflicting" if len(found) > 1 else
                  "ineligible_or_unavailable" if found else "missing")
        tests.append({"rq": rq, "p_value": p, "status": status})
    ordered = sorted(range(3), key=lambda i: tests[i]["p_value"]
                     if tests[i]["p_value"] is not None else 1.0)
    previous = 0.0
    for rank, index in enumerate(ordered):
        raw = tests[index]["p_value"]
        adjusted = min(1.0, max(previous, (3 - rank) * (raw if raw is not None else 1.0)))
        previous = adjusted
        tests[index].update(p_holm=adjusted if raw is not None else None,
                            reject_005=bool(raw is not None and adjusted <= .05))
    return {"method": "Holm", "family_size": 3, "split": split, "alpha": .05,
            "missing_test_policy": "Retain family slot at p=1; report adjusted p as null",
            "tests": tests}


def summarize_variant(directory, requested_split="auto"):
    warnings = []
    metadata = mapping(read(directory / "variant.json", warnings))
    config = mapping(metadata.get("config", metadata.get("parameters")))
    split = config.get("split", "val") if requested_split == "auto" else requested_split
    if split not in ("val", "test"):
        warnings.append(f"Invalid metadata split {split!r}; using val")
        split = "val"
    names = ("tokens", "tokens_learned_val", "tokens_learned_test", "pressure", "style")
    payloads = {name: read(directory / "results" / f"{name}.json", warnings) for name in names}
    token_row = choose(payloads["tokens"], split, warnings, "tokens.json", allow_all=True)
    token_details = mapping(token_row.get("details"))
    grammar_row = choose(payloads[f"tokens_learned_{split}"], split, warnings,
                         f"tokens_learned_{split}.json")
    grammar = mapping(grammar_row.get("details"))
    if not grammar:
        grammar = mapping(mapping(token_details.get("evaluations")).get(f"learned_{split}"))
    grammar_metrics = mapping(grammar_row.get("metrics"))
    pressure_row = choose(payloads["pressure"], split, warnings, "pressure.json")
    pressure = mapping(pressure_row.get("details"))
    models = mapping(pressure.get("models"))
    style_row = choose(payloads["style"], split, warnings, "style.json")
    style = mapping(style_row.get("details"))
    candidates = defaultdict(list)
    for payload in payloads.values():
        for row in rows(payload):
            if row.get("is_baseline"):
                continue
            confirmatory = mapping(mapping(row.get("details")).get("confirmatory"))
            if confirmatory:
                key = (confirmatory.get("split", row.get("split")),
                       confirmatory.get("rq", confirmatory.get("id")))
                candidates[key].append(confirmatory)
    family = holm(candidates, split)
    gated = {test["rq"]: test["p_value"] for test in family["tests"]}
    rq1 = {"status": token_details.get("status", grammar.get("status", "missing")),
           "grammar_status": grammar.get("status", "missing"),
           "excess_gain_bits": finite(grammar.get("excess_gain_bits", grammar_metrics.get("excess_gain_bits"))),
           "predictive_gain_bits": finite(grammar.get("predictive_gain_bits", grammar_metrics.get("predictive_gain_bits"))),
           "null_gain_bits": finite(grammar.get("null_gain_bits")), **interval(grammar),
           "p_value": pvalue(grammar.get("p_value", grammar_metrics.get("p_value"))),
           "confirmatory_p_value": gated["RQ1"], "n_series": grammar.get("n_series")}
    rq3 = {"status": pressure.get("status", "missing"),
           "interaction": pressure_effect(models.get("uncovered")),
           "third_depth": pressure_effect(models.get("third_depth")),
           "coverage": pressure_effect(models.get("coverage")),
           "confirmatory_p_value": gated["RQ3"], "estimand": pressure.get("estimand"),
           "measurement_gate": pressure.get("measurement_gate"), "reason": pressure.get("reason")}
    rq4 = {"status": style.get("status", "missing"), "effect": finite(style.get("effect")),
           **interval(style), "p_value": pvalue(style.get("p_value")),
           "confirmatory_p_value": gated["RQ4"], "reason": style.get("reason"),
           "measurement_gate": style.get("measurement_gate")}
    status = metadata.get("status", "unknown")
    if not metadata:
        warnings.append("Missing variant.json; seed/config cannot be inferred reliably")
    return {"variant": metadata.get("variant", directory.name), "directory": str(directory),
            "job_id": metadata.get("job_id"), "seed": config.get("seed"), "config": config,
            "compact": mapping(metadata.get("compact")), "split": split,
            "run_status": status, "provisional": status != "complete",
            "rq1": rq1, "rq3": rq3, "rq4": rq4, "confirmatory": family,
            "warnings": warnings}


def comparison_key(variant):
    # Compute allocation does not define the scientific sensitivity. Keep all
    # other recorded settings, including fitting epochs and sampling limits.
    excluded = {"seed", "workers", "device", "job_id", "variant", "run", "output",
                "compact_source", "reuse_compact", "cohort_id"}
    config = {key: value for key, value in variant["config"].items() if key not in excluded}
    if isinstance(config.get("tasks"), list):
        config["tasks"] = sorted(config["tasks"])
    if isinstance(config.get("tasks"), str):
        config["tasks"] = sorted(config["tasks"].replace(",", " ").split())
    config["split"] = variant["split"]
    compact = variant["compact"]
    cohort = compact.get("cohort_id", variant["config"].get("cohort_id"))
    # Unknown cohorts cannot silently become a claimed same-corpus seed study.
    cohort = cohort or "unknown:" + variant["directory"]
    return json.dumps({"config": config, "compact_cohort_id": cohort,
                       "extraction_signature": compact.get("extraction_signature")}, sort_keys=True)


def sign_consistency(variants):
    groups = defaultdict(list)
    for variant in variants:
        if not variant["provisional"] and variant["seed"] is not None:
            groups[comparison_key(variant)].append(variant)
    output = []
    metrics = ("rq1_excess_gain_bits", "rq1_predictive_gain_bits", "rq3_interaction",
               "rq3_third_depth", "rq3_coverage", "rq4_effect")
    for key, members in sorted(groups.items()):
        by_seed = defaultdict(list)
        for variant in members:
            by_seed[str(variant["seed"])].append(variant)
        unique = {seed: rows[0] for seed, rows in by_seed.items() if len(rows) == 1}
        report = {**json.loads(key), "group_id": hashlib.sha256(key.encode()).hexdigest()[:12],
                  "variants": [v["directory"] for v in members], "n_distinct_seeds": len(by_seed),
                  "excluded_duplicate_seeds": [seed for seed, rows in sorted(by_seed.items()) if len(rows) > 1],
                  "metrics": {}}
        for metric in metrics:
            estimates, eligible = {}, []
            for seed, variant in sorted(unique.items()):
                rq, field = metric.split("_", 1)
                if rq == "rq3":
                    estimate = variant[rq][field]["estimate"]
                else:
                    estimate = variant[rq][field]
                if estimate is not None:
                    estimates[seed] = estimate
                    if variant[rq]["confirmatory_p_value"] is not None:
                        eligible.append(seed)
            counts = {"positive": 0, "negative": 0, "zero": 0}
            for estimate in estimates.values():
                counts["positive" if estimate > 0 else "negative" if estimate < 0 else "zero"] += 1
            n = len(estimates)
            report["metrics"][metric] = {
                "n_seeds": n, **counts, "missing_seeds": sorted(set(unique) - set(estimates)),
                "estimates_by_seed": estimates, "inference_eligible_seeds": eligible,
                "sign_consistent": (counts["positive"] == n or counts["negative"] == n) if n >= 2 else None,
                "dominant_sign_fraction": max(counts.values()) / n if n else None,
                "interpretation": "Descriptive sign agreement; at least two distinct seeds required. Secondary pressure outcomes remain exploratory."}
        output.append(report)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("robust"), help="Directory containing isolated variant jobs")
    parser.add_argument("--output", type=Path, default=Path("results/robustness.json"), help="Only output file written")
    parser.add_argument("--split", choices=("auto", "val", "test"), default="auto",
                        help="auto uses each variant.json config.split (default val)")
    args = parser.parse_args(argv)
    directories = sorted(path for path in args.root.glob("*")
                         if path.is_dir() and (path / "results").is_dir())
    variants = [summarize_variant(directory, args.split) for directory in directories]
    payload = {"schema_version": 1, "generated": datetime.now(timezone.utc).isoformat(),
               "root": str(args.root), "split": args.split, "variants": variants,
               "sign_consistency": sign_consistency(variants),
               "notes": ["RQ1 excess_gain_bits CI is the reported whole-series bootstrap interval; predictive gain has no invented CI.",
                         "RQ3 interaction is uncovered-fraction late-by-trailing coefficient; third_depth and coverage are secondary.",
                         "Holm is applied separately per variant over RQ1/RQ3/RQ4 and uses only explicitly gated confirmatory p-values.",
                         "No multiplicity correction across sensitivity variants; robustness is not an additional discovery family.",
                         "Seed signs are descriptive, restricted to completed runs with identical non-seed scientific settings and compact cohort.",
                         "Duplicate jobs for one seed are excluded from sign counts; missing metadata/cohorts are not guessed."]}
    atomic_json(args.output, payload)
    print(f"Wrote {args.output}: {len(variants)} variants, {len(payload['sign_consistency'])} seed groups")


if __name__ == "__main__":
    main()
