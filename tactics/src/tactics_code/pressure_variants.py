"""Preregistered P6 symmetry, overtime and definition contrasts (validation only).

All estimates describe associations. Production constants are intentionally not
CLI options. This module imports pressure helpers without modifying that module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from . import pressure as pressure_module
from .common import atomic_json
from .events import guard_path
from .pressure import (last_man_arrays, regression_design, series_context_summary,
                       summarize_replay)
from .stats import bootstrap_ols, cluster_ols

N_BOOTSTRAP = 2000
SEED = 42
LATE_SECONDS = 60
REGULATION_MAX = 180
GOAL_OFFSET = 5120.0
VAL_SEASON = "rlcs-2025"
EXTRA_RESPONSES = ("centroid_y_own", "mean_three_player_depth")
REQUIRED = {"players", "ball", "roles", "live", "score_diff", "remaining", "overtime"}
CONTRASTS = {
    "p6_1_leading_late_minus_early": ("last_man_y_own", "leading"),
    "p6_1_trailing_late_minus_early": ("last_man_y_own", "trailing"),
    "p6_1_trailing_minus_leading_interaction": ("last_man_y_own", "interaction"),
    "p6_6_ot_minus_late_tied": ("last_man_y_own", "ot_minus_tied"),
    "p6_6_late_trailing_minus_ot": ("last_man_y_own", "trailing_minus_ot"),
    "p6_7_centroid_interaction": (EXTRA_RESPONSES[0], "interaction"),
    "p6_7_mean_depth_interaction": (EXTRA_RESPONSES[1], "interaction"),
}


def check_val(frame):
    if not frame.empty and not (frame["season"].eq(VAL_SEASON).all()
                                and frame["split"].eq("val").all()):
        raise ValueError("Only the preregistered validation season/split is allowed")


def definition_arrays(arrays):
    """Same availability mask as the last defender; no second team rotation.

    Centroid y is the signed field coordinate. Mean depth is the arithmetic
    mean longitudinal distance from the own goal line, not ball-relative depth.
    These definitions differ by a constant and provide one distinct check.
    """
    valid = last_man_arrays(arrays)["last_man_valid"]
    y = np.asarray(arrays["players"], float)[:, :3, 1]
    centroid = np.where(valid, y.mean(axis=1), np.nan)
    depth = np.where(valid, (y + GOAL_OFFSET).mean(axis=1), np.nan)
    return dict(zip(EXTRA_RESPONSES, (centroid, depth)))


def summarize_variants(meta, arrays):
    """Reuse the exact pressure context bins and response availability rules.

    The second pressure call substitutes the centroid for all own-player y's.
    Its last-man response therefore supplies centroid sufficient sums. Only
    that response is used: original covariates/other responses stay untouched.
    All replacements operate on new allocations, including for mmap input.
    """
    check_val(pd.DataFrame([meta]))
    # The inherited summarizer casts context codes to integer bins. Quarantine
    # malformed fractional codes first so they cannot become tied/regulation.
    score = np.asarray(arrays["score_diff"], float)
    ot = np.asarray(arrays["overtime"], float)
    remaining = np.asarray(arrays["remaining"], float)
    arrays = {**arrays,
              "score_diff": np.where(np.isfinite(score) & (score == np.floor(score)), score, np.nan),
              "overtime": np.where(np.isin(ot, [0., 1.]), ot, np.nan),
              "remaining": np.where(np.isfinite(remaining) & (remaining >= 0), remaining, np.nan)}
    rows = summarize_replay(meta, arrays, LATE_SECONDS)
    if not rows:
        return rows
    definitions = definition_arrays(arrays)
    players = np.array(arrays["players"], dtype=float, copy=True)
    players[:, :3, 1] = definitions["centroid_y_own"][:, None]
    centroid_rows = summarize_replay(meta, {**arrays, "players": players}, LATE_SECONDS)
    if len(rows) != len(centroid_rows):
        raise AssertionError("Pressure context grouping changed")
    for row, centroid in zip(rows, centroid_rows):
        for key in ("score_diff", "time_bin", "overtime", "ball_zone", "late", "zero_second"):
            if not (row[key] == centroid[key] or pd.isna(row[key]) and pd.isna(centroid[key])):
                raise AssertionError("Pressure context ordering changed")
        row["centroid_y_own"] = centroid["last_man_y_own"] - GOAL_OFFSET
        row["mean_three_player_depth"] = centroid["last_man_y_own"]
        for name in EXTRA_RESPONSES:
            row[name + "_n"] = centroid["last_man_y_own_n"]
    return rows


def aggregate_variants(observations):
    if observations.empty:
        return observations.copy()
    summary = series_context_summary(observations)
    for name in EXTRA_RESPONSES:
        alternate = observations.assign(last_man_y_own=observations[name],
                                        last_man_y_own_n=observations[name + "_n"])
        aggregated = series_context_summary(alternate)
        summary[name] = aggregated["last_man_y_own"].to_numpy(copy=True)
        summary[name + "_n"] = aggregated["last_man_y_own_n"].to_numpy(copy=True)
    return summary


def reparameterize(x, weights):
    """Make a linear contrast one coefficient, retaining its full covariance.

    This lets the unchanged CR1 and whole-series bootstrap implementations
    estimate sums/differences of coefficients without summing marginal SEs.
    """
    weights = np.asarray(weights, float)
    pivot = int(np.flatnonzero(weights)[0])
    transform = np.eye(x.shape[1])
    transform[pivot] = weights
    return x @ np.linalg.inv(transform), pivot


def unavailable(response, reason, data, support=None):
    return {"status": "not_estimable", "response": response, "reason": reason,
            "estimate": None, "se": None, "p_value": None,
            "ci_low": None, "ci_high": None,
            "n_series": int(data.series_id.nunique()) if "series_id" in data else 0,
            "n_rows": len(data), "cell_series": support or {},
            "series_bootstrap": {"ci_low": None, "ci_high": None,
                                 "requested_replicates": N_BOOTSTRAP,
                                 "successful_replicates": 0}}


def estimate(data, x, names, weights, response, support, omitted=()):
    try:
        design, coefficient = reparameterize(x, weights)
        y = data[response].to_numpy(float)
        fit = cluster_ols(design, y, data.series_id)
        boot = bootstrap_ols(design, y, data.series_id, coefficient, N_BOOTSTRAP, SEED)
        beta, se = float(fit["beta"][coefficient]), float(fit["se"][coefficient])
        critical = float(student_t.ppf(.975, fit["n_series"] - 1))
        # Keep numerical diagnostics even if some draws lose identification.
        # Such intervals cannot trigger a directional finding.
        complete = boot["successful_replicates"] == N_BOOTSTRAP
        return {"status": "fit" if complete else "bootstrap_incomplete",
                "response": response, "estimate": beta, "se": se,
                "p_value": float(fit["p"][coefficient]),
                "ci_low": boot["ci_low"], "ci_high": boot["ci_high"],
                "cr1_ci_low": beta - critical * se, "cr1_ci_high": beta + critical * se,
                "n_series": int(fit["n_series"]), "n_rows": len(data),
                "cell_series": support, "covariates": names,
                "contrast_weights": dict(zip(names, map(float, weights))),
                "omitted_covariates": list(omitted), "series_bootstrap": boot}
    except (ValueError, np.linalg.LinAlgError) as exc:
        return unavailable(response, str(exc), data, support)


def regulation_contrasts(summary, response):
    check_val(summary)
    if summary.empty or response not in summary:
        empty = unavailable(response, "No validation observations", summary)
        return {key: dict(empty) for key in ("leading", "trailing", "interaction")}
    selected = summary.loc[summary.series_id.notna() & summary.overtime.eq(0)
                           & summary.score_diff.isin([-1, 1]) & summary.remaining.gt(0)
                           & summary.remaining.le(REGULATION_MAX)
                           & np.isfinite(summary[response])].copy()
    cells = selected.groupby(["late", "score_diff"]).series_id.nunique()
    support = {f"late={int(a)},score={int(b)}": int(n) for (a, b), n in cells.items()}
    if len(cells) != 4 or min(cells) < 3:
        empty = unavailable(response, "Need independent series in every regulation cell", selected, support)
        return {key: dict(empty) for key in ("leading", "trailing", "interaction")}
    try:
        data, x, names, omitted = regression_design(selected)
    except (ValueError, np.linalg.LinAlgError) as exc:
        empty = unavailable(response, str(exc), selected, support)
        return {key: dict(empty) for key in ("leading", "trailing", "interaction")}
    outputs = {}
    # Definition checks only need the interaction, avoiding unnecessary draws.
    kinds = ("leading", "trailing", "interaction") if response == "last_man_y_own" else ("interaction",)
    for kind in kinds:
        weights = np.array([float((name == "late" and kind in ("leading", "trailing"))
                                  or (name == "late_trailing" and kind in ("trailing", "interaction")))
                            for name in names])
        outputs[kind] = estimate(data, x, names, weights, response, support, omitted)
    return outputs


def overtime_contrasts(summary):
    """Pairwise categorical OLS on the same equal-weight series/context unit.

    P6.6 specifies state contrasts, not the regulation interaction adjustment.
    Each pair is an intercept plus a state indicator. No countdown polynomial
    is extrapolated to overtime. Only known tied live OT is admitted; regulation
    at exactly zero is included here by the registered <= late-time definition.
    """
    check_val(summary)
    response = "last_man_y_own"
    keys = ("ot_minus_tied", "trailing_minus_ot")
    if summary.empty:
        return {key: unavailable(response, "No validation observations", summary) for key in keys}
    late = summary.overtime.eq(0) & summary.remaining.between(0, LATE_SECONDS)
    states = np.select([summary.overtime.eq(1) & summary.score_diff.eq(0),
                        late & summary.score_diff.eq(0), late & summary.score_diff.eq(-1)],
                       ["ot", "late_tied", "late_trailing"], default="excluded")
    source = summary.assign(state=states)
    out = {}
    for key, positive, reference in ((keys[0], "ot", "late_tied"),
                                     (keys[1], "late_trailing", "ot")):
        data = source.loc[source.state.isin([positive, reference]) & source.series_id.notna()
                          & np.isfinite(source[response])].copy()
        support = {state: int(data.loc[data.state.eq(state), "series_id"].nunique())
                   for state in (reference, positive)}
        if min(support.values()) < 3:
            out[key] = unavailable(response, "Insufficient independent series in a state", data, support)
            continue
        x = np.column_stack([np.ones(len(data)), data.state.eq(positive).to_numpy(float)])
        out[key] = estimate(data, x, ["intercept", positive], [0., 1.], response, support)
    return out


def direction(model):
    if model["status"] != "fit":
        return None
    if model["ci_low"] > 0:
        return "positive"
    if model["ci_high"] < 0:
        return "negative"
    return "unresolved"


def analyze(summary):
    check_val(summary)
    fits = {name: regulation_contrasts(summary, name)
            for name in ("last_man_y_own", *EXTRA_RESPONSES)}
    ot = overtime_contrasts(summary)
    contrasts = {key: (ot[kind] if key.startswith("p6_6") else fits[response][kind])
                 for key, (response, kind) in CONTRASTS.items()}
    baseline = direction(contrasts["p6_1_trailing_minus_leading_interaction"])
    for key, model in contrasts.items():
        model["direction"] = direction(model)
        if key.startswith("p6_7"):
            model["matches_last_man_direction_with_ci_excluding_zero"] = bool(
                baseline in ("positive", "negative") and direction(model) == baseline)
    return {"contrasts": contrasts,
            "decisions": {
                "leading_retreats": direction(contrasts["p6_1_leading_late_minus_early"]) == "negative",
                "ot_equivalent_to_late_tied": None,
                "ot_interpretation": "No equivalence margin was preregistered; an interval spanning zero does not establish similarity.",
                "registered_interpretation_table": {
                    "forward_shift_only_trailing_with_clock": "score-and-time association",
                    "ot_similar_to_late_tied": "clock-insensitive association; similarity is not formally tested"}},
            "method": "OLS; series-clustered CR1 t tests; percentile whole-series bootstrap intervals",
            "weighting": "Equal team-series-context rows, as in pressure.fit_pressure; no frame weights in OLS",
            "bootstrap": {"replicates": N_BOOTSTRAP, "seed": SEED,
                          "unit": "series_id; both teams and every available replay remain together"},
            "scope": {"split": "val", "season": VAL_SEASON, "held_out_opened": False,
                      "train_fitted_parameters": [],
                      "freezing": "No learned thresholds or nuisance predictions. Fixed registered cutoffs. Pressure design centering/scaling is algebraic reparameterization, not learned prediction."},
            "definitions": {"late_seconds": LATE_SECONDS, "regulation_max_seconds": REGULATION_MAX,
                            "goal_offset": GOAL_OFFSET, "centroid_y_own": "mean own-player y",
                            "mean_three_player_depth": "mean(own-player y + own-goal offset)",
                            "definition_alias": "The two definition contrasts are algebraically identical, not independent evidence",
                            "p6_1_p6_7_zero_second": "excluded, matching pressure.fit_pressure",
                            "p6_6_zero_second": "included by the registered regulation <= late cutoff",
                            "p6_6_ot": "known overtime and tied score; unknown/non-tied OT excluded"},
            "limitations": ["Associational contrasts; raw p values, no new multiplicity claim",
                            "P6.6 uses pairwise unadjusted state OLS; P6.1/P6.7 retain the pressure covariates",
                            "No preregistered equivalence margin for the overtime interpretation",
                            "Bootstrap covers all available compact members; external complete-series membership is not certified",
                            "Unknown demolition duration and stale compact tracks remain measurement limitations"]}


def inventory(root):
    """Validate every selected metadata row BEFORE opening any numeric shard.

    Never recursively discover seasons or open train/test metadata. Check both
    lexical paths and symlink destinations, including individual shards.
    """
    root = guard_path(root)
    directory = guard_path(root / VAL_SEASON)
    if not directory.is_dir():
        raise ValueError("Missing validation compact directory")
    shards, seen, replay_pairs = [], set(), {}
    for metadata in sorted(directory.glob("compact-*.parquet")):
        metadata = guard_path(metadata)
        shard = guard_path(metadata.with_suffix(".npz"))
        frame = pd.read_parquet(metadata)
        check_val(frame)
        if frame.empty:
            continue
        for row in frame.to_dict("records"):
            if not isinstance(row.get("series_id"), str) or not row["series_id"]:
                raise ValueError("Known series IDs required")
            pair = (row["replay_id"], row["focal_team"])
            if pair in seen or row["focal_team"] not in (0, 1):
                raise ValueError("Duplicate or invalid replay perspective")
            seen.add(pair)
            replay_pairs.setdefault(row["replay_id"], []).append(row)
            if int(row["start"]) != row["start"] or int(row["stop"]) != row["stop"] or not 0 <= row["start"] < row["stop"]:
                raise ValueError("Invalid compact slice bounds")
        if not shard.is_file():
            raise ValueError("Missing paired numeric shard")
        shards.append((metadata, shard, frame))
    for pair in replay_pairs.values():
        if len(pair) != 2 or len({row["series_id"] for row in pair}) != 1:
            raise ValueError("Both focal perspectives in one series are required")
    if not shards:
        raise ValueError("No validation compact metadata")
    return shards


def run(compact, output, artifacts):
    started = time.perf_counter()
    compact, output, artifacts = map(guard_path, (compact, output, artifacts))
    for destination in (output, artifacts):
        if destination.resolve() == compact.resolve() or compact.resolve() in destination.resolve().parents:
            raise ValueError("Outputs must not modify the input compact")
    shards = inventory(compact)
    timing = {"inventory_seconds": time.perf_counter() - started}
    extraction = guard_path(compact / "extraction.json")
    manifest = json.loads(extraction.read_text()) if extraction.is_file() else {}
    if manifest.get("synthetic_fixture") is not True:
        manifest["synthetic_fixture"] = False
    records, sources, states = [], [], set()
    frame_count = 0
    tick = time.perf_counter()
    for metadata, shard, frame in shards:
        with np.load(shard, allow_pickle=False) as loaded:
            if not REQUIRED <= set(loaded.files):
                raise ValueError("Missing required pressure arrays")
            arrays = {key: loaded[key] for key in REQUIRED | ({"role_uncertain"} & set(loaded.files))}
        lengths = {len(a) for a in arrays.values()}
        if len(lengths) != 1 or frame.stop.max() > min(lengths):
            raise ValueError("Compact array lengths disagree with metadata")
        # Deliberately exercise the same immutable views as mmap/slice readers.
        for value in arrays.values():
            value.flags.writeable = False
        for meta in frame.to_dict("records"):
            start, stop = int(meta["start"]), int(meta["stop"])
            records.extend(summarize_variants(meta, {key: a[start:stop] for key, a in arrays.items()}))
            frame_count += stop - start
            states.add(str(meta.get("state_source", "unknown")))
        sources.append({"metadata": str(metadata), "arrays": str(shard),
                        "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
                        "array_bytes": shard.stat().st_size, "array_mtime_ns": shard.stat().st_mtime_ns})
    timing["load_and_summarize_seconds"] = time.perf_counter() - tick
    tick = time.perf_counter()
    summary = aggregate_variants(pd.DataFrame.from_records(records))
    artifacts.mkdir(parents=True, exist_ok=True)
    summary_path = artifacts / "series_context.parquet"
    summary.to_parquet(summary_path, index=False)
    timing["aggregate_and_save_seconds"] = time.perf_counter() - tick
    tick = time.perf_counter()
    result = analyze(summary)
    timing["inference_seconds"] = time.perf_counter() - tick
    timing["total_seconds"] = time.perf_counter() - started
    result.update(data_kind="synthetic_self_test" if manifest["synthetic_fixture"] else "validation_compact",
                  empirical_result=not manifest["synthetic_fixture"], timing=timing,
                  measurement_gate={"passed": states == {"explicit_state_map"},
                                    "requirement": "Every evaluated replay uses an explicit audited state map",
                                    "interpretation": "Unverified state provenance limits interpretation to exploratory diagnostics"},
                  provenance={"sources": sources, "summary": str(summary_path),
                              "extraction_manifest": str(extraction) if extraction.is_file() else None,
                              "state_sources": sorted(states), "perspectives": sum(len(f) for _, _, f in shards),
                              "frames": frame_count, "context_rows": len(summary),
                              "pressure_module_sha256": hashlib.sha256(Path(pressure_module.__file__).read_bytes()).hexdigest(),
                              "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    atomic_json(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", type=Path)
    parser.add_argument("--out", type=Path, default=Path("results/p6_variants.json"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/p6-variants"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        import importlib.util
        import unittest
        tests = Path(__file__).resolve().parents[1] / "tests" / "test_pressure_variants.py"
        spec = importlib.util.spec_from_file_location("p6_self_tests", tests)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.OUTPUT_ROOT = args.artifacts.parent
        outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
        if not outcome.wasSuccessful():
            raise SystemExit(1)
        compact = module.write_fixture(args.artifacts / "synthetic_compact")
        result = run(compact, args.out, args.artifacts)
        if any(value["status"] != "fit" for value in result["contrasts"].values()):
            raise AssertionError("Synthetic full-bootstrap pipeline did not fit every contrast")
    else:
        if args.compact is None:
            parser.error("--compact is required except with --self-test")
        result = run(args.compact, args.out, args.artifacts)
    print(json.dumps({"output": str(args.out), "data_kind": result["data_kind"],
                      "timing": result["timing"]}, indent=2))


if __name__ == "__main__":
    main()
