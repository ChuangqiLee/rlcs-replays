"""RQ3: geometric cover and the predeclared late-by-score interaction.

Unknown score or overtime is never encoded as tied regulation. Inference uses
team-series-context summaries, with complete series as the uncertainty unit.
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

from .common import Run, add_common_args
from .data import iter_compact
from .stats import bootstrap_ols, cluster_ols, update_confirmatory_family


def last_man_arrays(arrays, field_half_length=5120.0):
    """Literal defensive line in the compact focal-team frame (+y attacks).

    Own slots are 0:3 after extract_replay's team rotation. The minimum
    own-player y is the defensive-most car, regardless of ball proximity.
    last_man_y_own = min(y_own) + field_half_length is signed longitudinal
    distance from the own goal line (not Euclidean distance to goal).
    last_man_behind_ball = ball_y - min(y_own) is positive when goal-side
    of the ball. Missing/known-demolished own players invalidate the line:
    an absent deepest player must not spuriously appear advanced.
    Unknown demolition duration in legacy compacts remains a measurement
    limitation; callers must also audit stale tracks/availability.
    This additive helper does not alter the original pressure estimands.
    """
    players = np.asarray(arrays["players"], float)[:, :3]
    ball = np.asarray(arrays["ball"], float)
    present = np.isfinite(players[:, :, :3]).all(axis=2)
    valid = present.all(axis=1) & ~(players[:, :, 7] == 1).any(axis=1)
    safe_y = np.where(present, players[:, :, 1], np.inf)
    index = np.argmin(safe_y, axis=1)
    own_y = safe_y[np.arange(len(players)), index]
    own_y = np.where(valid, own_y, np.nan)
    return {"last_man_y_own": own_y + field_half_length,
            "last_man_behind_ball": ball[:, 1] - own_y,
            "last_man_index": np.where(valid, index, -1).astype(np.int8),
            "last_man_valid": valid}


def cover_arrays(arrays, field_half_length=5120.0, field_width=8192.0):
    """Planar own-goal-to-ball corridor; heights do not imply a reachable save."""
    ball = np.asarray(arrays["ball"], float)
    players = np.asarray(arrays["players"], float)[:, :3]
    pos = players[:, :, :3]
    goal = np.array([0.0, -field_half_length])
    segment = ball[:, :2] - goal
    denom = np.sum(segment ** 2, axis=1)
    valid_ball = np.isfinite(ball[:, :3]).all(axis=1) & (denom > 1e-9)
    present = np.isfinite(pos).all(axis=2)
    demolished = players[:, :, 7] == 1
    known = (present | demolished).all(axis=1) & valid_ball
    relative = pos[:, :, :2] - goal
    with np.errstate(invalid="ignore", divide="ignore"):
        projection = np.einsum("tpi,ti->tp", relative, segment) / denom[:, None]
    perpendicular = relative - projection[:, :, None] * segment[:, None, :]
    lateral = np.linalg.norm(perpendicular, axis=2)
    covers = ((projection >= 0) & (projection <= 1) & (lateral <= .1 * field_width)
              & present & ~demolished & valid_ball[:, None])
    count = np.where(known, covers.sum(axis=1), np.nan).astype(float)
    player_cover = np.where(present & valid_ball[:, None], covers.astype(float), np.nan)
    player_cover[demolished] = 0
    depth = ball[:, None, 1] - pos[:, :, 1]
    depth[~present | demolished] = np.nan
    rank = np.asarray(arrays["roles"])
    third = np.where(rank == 2, depth, np.nan)
    has_third = np.sum((rank == 2) & np.isfinite(depth), axis=1) == 1
    third_depth = np.where(has_third, np.nansum(third, axis=1), np.nan)
    third_depth[np.asarray(arrays.get("role_uncertain", np.zeros(len(ball), bool)), bool)] = np.nan
    distances = np.stack([np.linalg.norm(pos[:, i, :2] - pos[:, j, :2], axis=1)
                          for i, j in ((0, 1), (0, 2), (1, 2))], axis=1)
    spacing = np.where(present.all(axis=1) & ~demolished.any(axis=1), distances.mean(axis=1), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_boost = np.nanmean(players[:, :, 6], axis=1)
    return {"third_depth": third_depth, "coverage": count,
            "uncovered": np.where(known, count == 0, np.nan).astype(float),
            "spacing": spacing, "ball_x": ball[:, 0], "ball_y": ball[:, 1],
            "ball_z": ball[:, 2], "ball_speed": np.linalg.norm(ball[:, 3:6], axis=1),
            "mean_boost": mean_boost, "player_cover": player_cover, "player_depth": depth}


MEASURES = ["third_depth", "coverage", "uncovered", "spacing", "ball_x", "ball_y",
            "ball_z", "ball_speed", "mean_boost"]
# Additive outputs: historical measures/models and their multiplicity family
# retain their definitions. Corrected responses form a separate exploratory pair.
CORRECTED_MEASURES = ["last_man_y_own", "last_man_behind_ball"]


def available_measures(frame):
    """Old saved summaries remain usable without invented corrected metrics."""
    return MEASURES + [name for name in CORRECTED_MEASURES if name in frame]


def summarize_replay(meta, arrays, late_threshold=60):
    """Each replay contributes sufficient sums to series/context summaries."""
    measures = cover_arrays(arrays)
    measures.update(last_man_arrays(arrays))
    live = np.asarray(arrays["live"], bool)
    if not live.any():
        return []
    score = np.asarray(arrays["score_diff"], float)
    remaining = np.asarray(arrays["remaining"], float)
    overtime = np.asarray(arrays["overtime"], float)
    # Unknown context has its own explicit category, retained for coverage audits.
    score_key = np.where(np.isfinite(score), np.clip(score, -3, 3), 99).astype(int)
    clock_key = np.where(np.isfinite(remaining), np.floor(np.maximum(0, remaining) / 30), -1).astype(int)
    ot_key = np.where(np.isfinite(overtime), overtime, -1).astype(int)
    zone = np.where(np.isfinite(measures["ball_y"]), np.digitize(measures["ball_y"], [-1707, 1707]), -1)
    late = np.where(np.isfinite(remaining), remaining <= late_threshold, -1).astype(int)
    zero_second = np.isfinite(remaining) & (remaining == 0)
    keys = np.stack([score_key, clock_key, ot_key, zone, late, zero_second.astype(int)], axis=1)
    groups, inverse = np.unique(keys[live], axis=0, return_inverse=True)
    indices = np.flatnonzero(live)
    records = []
    for g, (s, t, ot, z, is_late, is_zero) in enumerate(groups):
        take = indices[inverse == g]
        row = {k: meta.get(k) for k in ("season", "split", "series_id", "roster_id", "team_id", "event", "region")}
        row.update(replay_id=meta["replay_id"], focal_team=meta["focal_team"],
                   score_diff=float(s) if s != 99 else np.nan,
                   overtime=float(ot) if ot >= 0 else np.nan,
                   time_bin=int(t), ball_zone=int(z), late=int(is_late),
                   frame_weight=len(take), remaining=float(np.nanmean(remaining[take])),
                   zero_second=bool(is_zero))
        for key in MEASURES + CORRECTED_MEASURES:
            vals = measures[key][take]
            finite = np.isfinite(vals)
            row[key] = float(vals[finite].mean()) if finite.any() else np.nan
            row[key + "_n"] = int(finite.sum())
        records.append(row)
    return records


def series_context_summary(observations):
    if observations.empty:
        return observations
    keys = ["split", "season", "series_id", "roster_id", "team_id", "event", "region",
            "score_diff", "overtime", "time_bin", "ball_zone", "late", "zero_second"]
    work = observations.copy()
    work["remaining_sum"] = work.remaining * work.frame_weight
    measures = available_measures(work)
    for name in measures:
        work[name + "_sum"] = work[name].fillna(0) * work[name + "_n"]
    sums = ["frame_weight", "remaining_sum"] + [x + suffix for x in measures for suffix in ("_sum", "_n")]
    out = work.groupby(keys, dropna=False, observed=True)[sums].sum().reset_index()
    out["remaining"] = out.pop("remaining_sum") / out.frame_weight
    for name in measures:
        out[name] = out.pop(name + "_sum") / out[name + "_n"].replace(0, np.nan)
    return out


def regression_design(frame):
    """Protect the confirmatory coefficient; drop only redundant nuisance terms."""
    data = frame.copy()
    data["trailing"] = (data.score_diff < 0).astype(float)
    data["late_trailing"] = data.late * data.trailing
    names = ["intercept", "late", "trailing", "late_trailing"]
    cols = [np.ones(len(data)), data.late.to_numpy(float), data.trailing.to_numpy(float),
            data.late_trailing.to_numpy(float)]
    x = np.column_stack(cols)
    if np.linalg.matrix_rank(x) < 4:
        raise ValueError("the four late/earlier by trailing/leading cells are not all observed")
    omitted = []
    for name in ("remaining", "ball_x", "ball_y", "ball_z", "ball_speed", "mean_boost"):
        values = data[name].to_numpy(float)
        if not np.isfinite(values).all():
            omitted.append(name + ": missing values")
            continue
        if np.std(values) < 1e-9:
            continue
        standard = (values - values.mean()) / values.std()
        candidates = [(name, standard)]
        if name == "remaining":
            candidates.append(("remaining_squared", standard ** 2))
        for label, candidate in candidates:
            proposed = np.column_stack([x, candidate])
            if np.linalg.matrix_rank(proposed) == proposed.shape[1]:
                x, names = proposed, names + [label]
    # Roster fixed effects are feasible on moderate panels. Larger panels use
    # crossed random effects when available; fallback limitation is recorded.
    for name in ("season", "region", "roster_id"):
        levels = sorted(data[name].dropna().astype(str).unique())
        if name == "roster_id" and len(levels) > 80:
            omitted.append("roster fixed effects: >80 levels; see mixed-effects sensitivity")
            continue
        encoded = data[name].fillna("unknown").astype(str)
        for level in levels[1:]:
            candidate = (encoded == level).to_numpy(float)
            proposed = np.column_stack([x, candidate])
            if np.linalg.matrix_rank(proposed) == proposed.shape[1]:
                x, names = proposed, names + [name + "=" + level]
    return data, x, names, omitted


def mixed_effect_sensitivity(data, x, names, response, max_rows=20000):
    """Crossed roster and series random intercepts; independent convergence gate."""
    if len(data) > max_rows:
        return {"status": "not_fit", "reason": f"more than {max_rows} context rows; cluster-robust OLS used"}
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        return {"status": "unavailable", "reason": "statsmodels not installed"}
    if data.roster_id.isna().any():
        return {"status": "not_fit", "reason": "stable roster identity missing"}
    try:
        fit_data = data[["series_id", "roster_id", response]].copy()
        # Keep roster as a random effect, avoiding redundant roster fixed effects.
        use = [(i, f"x{i}") for i, name in enumerate(names)
               if i and not name.startswith("roster_id=")]
        for i, label in use:
            fit_data[label] = x[:, i]
        fit_data["all_groups"] = 1
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = smf.mixedlm(response + " ~ " + " + ".join(label for _, label in use),
                                fit_data, groups="all_groups", re_formula="0",
                                vc_formula={"series": "0 + C(series_id)", "roster": "0 + C(roster_id)"},
                                use_sparse=True)
            fitted = model.fit(reml=False, method="lbfgs", maxiter=150, disp=False)
        idx = "x" + str(names.index("late_trailing"))
        if not fitted.converged or not np.isfinite(fitted.params[idx]):
            raise ValueError("mixed model did not converge")
        interval = fitted.conf_int().loc[idx].to_numpy(float)
        return {"status": "fit", "method": "crossed roster/series random intercepts",
                "estimate": float(fitted.params[idx]), "se": float(fitted.bse[idx]),
                "p_value": float(fitted.pvalues[idx]), "ci_low": float(interval[0]), "ci_high": float(interval[1])}
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)[:400]}


def fit_pressure(summary, split="val", n_bootstrap=2000, seed=42, regression="auto", score_margin=1):
    selected = summary.loc[(summary.split == split) & summary.series_id.notna()
                           & (summary.overtime == 0) & summary.score_diff.isin([-score_margin, score_margin])
                           & (summary.remaining > 0) & (summary.remaining <= 180)].copy()
    if selected.empty:
        return {"status": "insufficient_data", "reason": "no known-score regulation observations in the declared contrast", "models": {},
                "corrected_models": {name: {"status": "insufficient_data", "reason": "no observations in declared contrast"}
                                     for name in CORRECTED_MEASURES}}
    # Equal team-series-context rows. Both focal teams stay in the same cluster.
    cells = selected.groupby(["late", "score_diff"]).series_id.nunique()
    support = {f"late={int(a)},score={int(b)}": int(n) for (a, b), n in cells.items()}
    if len(cells) != 4 or min(cells) < 3:
        return {"status": "insufficient_data", "reason": "need >=3 independent series in all four contrast cells", "cell_series": support, "models": {},
                "corrected_models": {name: {"status": "insufficient_data", "reason": "four-cell series support gate failed"}
                                     for name in CORRECTED_MEASURES}}
    models, corrected_models = {}, {}
    for response in ("uncovered", "third_depth", "coverage", "spacing", *CORRECTED_MEASURES):
        target = corrected_models if response in CORRECTED_MEASURES else models
        if response not in selected:
            target[response] = {"status": "unavailable",
                                "reason": "corrected response absent from saved summary; rerun compact summarization"}
            continue
        data = selected.loc[np.isfinite(selected[response])].copy()
        try:
            data, x, names, omitted = regression_design(data)
            y = data[response].to_numpy(float)
            fit = cluster_ols(x, y, data.series_id)
            i = names.index("late_trailing")
            boot = bootstrap_ols(x, y, data.series_id, i, n_bootstrap, seed)
            model = {"status": "fit", "method": "OLS with series-clustered CR1 uncertainty",
                     "estimate": float(fit["beta"][i]), "se": float(fit["se"][i]),
                     "p_value": float(fit["p"][i]), "n_series": int(fit["n_series"]),
                     "n_rows": len(data), "covariates": names, "omitted_covariates": omitted,
                     "series_bootstrap": boot}
            if response == "uncovered" and regression != "ols":
                mixed = mixed_effect_sensitivity(data, x, names, response)
                if mixed.get("status") == "fit":
                    model = {"status": "fit", "method": mixed["method"],
                             **{key: mixed[key] for key in ("estimate", "se", "p_value", "ci_low", "ci_high")},
                             "n_series": int(fit["n_series"]), "n_rows": len(data),
                             "covariates": names, "omitted_covariates": omitted,
                             "uncertainty": "MixedLM Wald interval; OLS whole-series bootstrap is a separate sensitivity estimand",
                             "ols_sensitivity": model}
                else:
                    model["mixed_effects"] = mixed
            target[response] = model
        except (ValueError, np.linalg.LinAlgError) as exc:
            target[response] = {"status": "insufficient_data", "reason": str(exc)}
    return {"status": "fit" if models.get("uncovered", {}).get("status") == "fit" else "insufficient_data",
            "cell_series": support, "models": models,
            "corrected_models": corrected_models,
            "corrected_response_definition": {
                "status": "exploratory observational association",
                "last_man_y_own": "minimum own-player y + 5120 uu; positive interaction is a line farther forward",
                "last_man_behind_ball": "ball y minus minimum own-player y; positive interaction is farther behind ball",
                "identity": "deepest own player at each frame; identity may change, so neither response is fixed-player displacement",
                "multiplicity": "separate exploratory pair; raw p-values and CIs, excluded from historical confirmatory and pooled exploratory families"},
            "estimand": f"[late-earlier, trailing by {score_margin}]-[late-earlier, leading by {score_margin}]",
            "primary_uncertainty": "Converged crossed MixedLM with Wald uncertainty when available; otherwise series-clustered OLS and whole-series bootstrap. OLS bootstrap accompanying MixedLM is a separately labelled sensitivity.",
            "limitations": ["observational association, not causal or psychological pressure",
                            "opponent historical strength unavailable; not silently imputed",
                            "zero-second live play and overtime are excluded from the regulation contrast",
                            "common support gate checks four cells; unmeasured confounding remains"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--split", choices=["val", "test"], default="val")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--late-threshold", type=float, default=60)
    parser.add_argument("--score-margin", type=int, choices=[1, 2], default=1,
                        help="Exact symmetric score contrast: -margin vs +margin (ties excluded)")
    parser.add_argument("--regression", choices=["auto", "ols"], default="auto")
    args = parser.parse_args(argv)
    if args.bootstrap < 0 or not 0 < args.late_threshold < 180:
        parser.error("bootstrap must be nonnegative and late threshold between 0 and 180")
    with Run(args, "pressure", method="Series-adjusted geometric cover") as run:
        _run(args, run)


def _run(args, run):
    run.idea("rq3-cover", "Pressure redistributes cover", "running", motivation="Predeclared late-by-score contrast")
    records = []
    state_sources = set()
    permitted = {"train", "val", "test"} if args.split == "test" else {"train", "val"}
    for i, (meta, arrays) in enumerate(iter_compact(args.input, splits=permitted)):
        # The test set is not opened by development jobs.
        if meta.get("split") == "test" and args.split != "test":
            continue
        if meta.get("split") == args.split:
            state_sources.add(str(meta.get("state_source") or "unknown"))
        records.extend(summarize_replay(meta, arrays, args.late_threshold))
        if (i + 1) % 100 == 0:
            run.metric(split=args.split, replay_perspectives=i + 1, summary_rows=len(records))
    folder = args.output / "artifacts" / "pressure"
    folder.mkdir(parents=True, exist_ok=True)
    observations = pd.DataFrame.from_records(records)
    if observations.empty:
        observations = pd.DataFrame(columns=["split", "season", "series_id", "roster_id", "team_id", "event", "region",
                                             "score_diff", "overtime", "time_bin", "ball_zone", "late", "zero_second",
                                             "remaining", "frame_weight", *MEASURES, *CORRECTED_MEASURES])
    summary = series_context_summary(observations)
    summary.to_parquet(folder / "observations.parquet", index=False)
    details = fit_pressure(summary, args.split, args.bootstrap, args.seed, args.regression, args.score_margin)
    details["pressure_definition"] = {"late_seconds": args.late_threshold, "score_margin": args.score_margin,
                                      "score_policy": "exact symmetric margins; ties excluded",
                                      "regulation_seconds": [0, 180]}
    metrics = {"context_rows": len(summary), "series": int(summary.series_id.nunique())}
    primary = details.get("models", {}).get("uncovered", {})
    if primary.get("status") == "fit":
        metrics.update(interaction=primary["estimate"], p_value=primary["p_value"])
    state_gate = state_sources == {"explicit_state_map"}
    details["measurement_gate"] = {"passed": state_gate, "state_sources": sorted(state_sources),
                                    "requirement": "Every evaluated replay uses an explicit audited state map; heuristic live play is exploratory"}
    details["confirmatory"] = {"rq": "RQ3", "split": args.split, "p_value": primary.get("p_value") if state_gate else None}
    # Descriptive pressure curves keep OT and zero-second play in separate rows.
    if not summary.empty:
        curve_keys = ["split", "time_bin", "score_diff", "overtime", "zero_second"]
        curves = summary.groupby(curve_keys, dropna=False, observed=True)[available_measures(summary)].mean().reset_index()
    else:
        curves = pd.DataFrame(columns=["split", "time_bin", "score_diff", "overtime", "zero_second", *MEASURES, *CORRECTED_MEASURES])
    curves.to_parquet(folder / "curves.parquet", index=False)
    run.metric(split=args.split, **metrics)
    run.result("pressure", metrics, split=args.split, details=details,
               notes="Primary response is uncovered fraction; depth, coverage count and spacing are exploratory. Known-score live regulation only.",
               lower_is_better=["p_value"])
    feasible = details["status"] == "fit" and state_gate
    run.idea("rq3-cover", "Pressure redistributes cover", "promising" if feasible else "pruned",
             prune_reason="" if feasible else ("Live-state measurement provenance is unverified" if not state_gate else details.get("reason", "Primary interaction is not estimable")),
             best_metric={"name": "interaction", "value": metrics["interaction"], "task": "pressure", "split": args.split} if feasible else None)
    update_confirmatory_family(args.output)


if __name__ == "__main__":
    main()
