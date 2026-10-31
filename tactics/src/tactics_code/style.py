"""RQ4: context-standardized roster persistence and descriptive player/meta drift."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

from .common import Run, add_common_args, read_json
from .data import iter_compact
from .pressure import cover_arrays
from .stats import update_confirmatory_family


def series_half(series_id, seed=42):
    """A global split keeps both perspectives and all games of a series together."""
    digest = hashlib.sha256(f"{seed}:{series_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 2


def context_columns(frame):
    """Context bins are fixed in advance and never optimized on test outcomes."""
    out = frame.copy()
    score = pd.to_numeric(out.score_diff, errors="coerce")
    clock = pd.to_numeric(out.remaining, errors="coerce")
    ot = pd.to_numeric(out.overtime, errors="coerce")
    ball_y = pd.to_numeric(out.ball_y, errors="coerce")
    valid = score.notna() & clock.notna() & ot.isin([0, 1]) & ball_y.notna()
    band = np.select([ot == 1, clock == 0, clock <= 60, clock <= 180],
                     ["overtime", "zero", "late", "middle"], default="early")
    score_band = np.sign(score.fillna(0)).astype(int).astype(str)
    zone = np.digitize(ball_y.fillna(0), [-1707, 1707]).astype(str)
    out["region"] = out.region.fillna("unknown").astype(str)
    out["context"] = out.region + "|" + score_band + "|" + band + "|" + zone
    out.loc[~valid, "context"] = None
    return out


def feature_columns(k):
    return [f"token_{i}" for i in range(k)] + ["third_depth", "coverage", "spacing"]


def window_features(windows, k):
    data = context_columns(windows)
    for token in range(k):
        data[f"token_{token}"] = (data.token == token).astype(float)
    # Fixed physical units avoid fitting normalizers to the held-out season.
    data["third_depth"] = data.third_depth / 5120
    data["coverage"] = data.coverage / 3
    data["spacing"] = data.spacing / 8192
    return data


def training_reference(data):
    reference = data.loc[(data.split == "train") & data.series_id.notna() & data.context.notna()]
    if reference.empty:
        return {}
    counts = reference.groupby(["series_id", "context"], observed=True).size().rename("n").reset_index()
    counts["weight"] = counts.n / counts.groupby("series_id").n.transform("sum")
    weights = counts.groupby("context").weight.sum()
    weights /= weights.sum()
    return weights.to_dict()


def build_series_table(data, features, seed):
    keep = data.loc[data.series_id.notna() & data.roster_id.notna() & data.context.notna()].copy()
    keep["half"] = keep.series_id.map(lambda value: series_half(value, seed))
    return keep.groupby(["roster_id", "half", "region", "context", "series_id"], observed=True)[features].mean().reset_index()


def standardize_table(series_table, features, support, reference, weights=None):
    """Equal-series estimates within context, then fixed training-context mixture."""
    if series_table.empty:
        return pd.DataFrame()
    work = series_table.loc[series_table.context.isin(support)].copy()
    work["weight"] = 1.0 if weights is None else work.series_id.map(weights).fillna(0)
    work = work.loc[work.weight > 0]
    keys = ["roster_id", "half", "region", "context"]
    means = []
    for group, rows in work.groupby(keys, observed=True):
        values = rows[features].to_numpy(float)
        if not np.isfinite(values).all():
            continue
        means.append(dict(zip(keys, group), **dict(zip(features, np.average(values, axis=0, weights=rows.weight)))))
    if not means:
        return pd.DataFrame()
    means = pd.DataFrame(means)
    target = np.array([reference[c] for c in support], float)
    target /= target.sum()
    fingerprints = []
    for (roster, half, region), rows in means.groupby(["roster_id", "half", "region"], observed=True):
        rows = rows.set_index("context")
        if not set(support).issubset(rows.index):
            continue
        values = np.average(rows.loc[support, features].to_numpy(float), axis=0, weights=target)
        fingerprints.append({"entity_type": "roster", "entity_id": roster, "roster_id": roster,
                             "half": int(half), "region": region, **dict(zip(features, values))})
    return pd.DataFrame(fingerprints)


def persistence_statistic(fingerprints, features, k, permutation=None):
    """Between-minus-within distance, using independent A/B series halves."""
    if fingerprints.empty:
        raise ValueError("no fingerprints on common context support")
    a = fingerprints.loc[fingerprints.half == 0].set_index("roster_id")
    b = fingerprints.loc[fingerprints.half == 1].set_index("roster_id")
    rosters = sorted(set(a.index) & set(b.index))
    if len(rosters) < 2:
        raise ValueError("need at least two rosters with both independent series halves")
    av = a.loc[rosters, features].to_numpy(dtype=float, copy=True)
    bv = b.loc[rosters, features].to_numpy(dtype=float, copy=True)
    # Hellinger coordinates for usage; geometrical descriptors retain fixed scales.
    av[:, :k] = np.sqrt(np.maximum(av[:, :k], 0)) / np.sqrt(2)
    bv[:, :k] = np.sqrt(np.maximum(bv[:, :k], 0)) / np.sqrt(2)
    if permutation is not None:
        bv = bv[permutation]
    distances = np.linalg.norm(av[:, None] - bv[None, :], axis=2)
    within = float(np.trace(distances) / len(rosters))
    between = float(distances[~np.eye(len(rosters), dtype=bool)].mean())
    return {"effect": between - within, "within_distance": within, "different_distance": between,
            "n_rosters": len(rosters)}


def evaluate_persistence(data, reference, features, k, min_series=20, min_events=3,
                         permutations=2000, bootstrap=2000, seed=42):
    rng = np.random.default_rng(seed)
    valid = data.loc[data.roster_id.notna() & data.series_id.notna() & data.context.notna()].copy()
    if valid.empty or not reference:
        return pd.DataFrame(), {"status": "insufficient_data", "reason": "known identities, context and training reference required"}
    eligibility = valid.groupby("roster_id").agg(series=("series_id", "nunique"), events=("event", "nunique"))
    eligible = eligibility.index[(eligibility.series >= min_series) & (eligibility.events >= min_events)]
    valid = valid.loc[valid.roster_id.isin(eligible)]
    table = build_series_table(valid, features, seed)
    # Event exposure and series-count precision must be comparable before
    # exchanging roster labels. Exact event sets plus a prespecified log2 count
    # band are conservative matching requirements, not outcome-selected strata.
    event_sets = valid.groupby("roster_id").event.apply(lambda values: tuple(sorted(set(values.dropna().astype(str)))))
    match = {roster: json.dumps([event_sets[roster], int(np.floor(np.log2(eligibility.loc[roster, "series"])))])
             for roster in eligible}
    table["matching_stratum"] = table.roster_id.map(match)
    region_results, all_fingerprints, region_specs = [], [], []
    for (region, matching_stratum), regional in table.groupby(["region", "matching_stratum"], observed=True):
        half_counts = regional.groupby(["roster_id", "half"]).series_id.nunique().unstack(fill_value=0)
        if 0 not in half_counts or 1 not in half_counts:
            continue
        candidates = half_counts.index[(half_counts[0] >= 2) & (half_counts[1] >= 2)]
        regional = regional.loc[regional.roster_id.isin(candidates)]
        if len(candidates) < 2:
            continue
        supports = [set(rows.context) for _, rows in regional.groupby(["roster_id", "half"], observed=True)]
        common = sorted(set.intersection(*supports) & set(reference))
        if not common:
            continue
        fp = standardize_table(regional, features, common, reference)
        try:
            observed = persistence_statistic(fp, features, k)
        except ValueError:
            continue
        fp["n_contexts"] = len(common)
        fp["support"] = json.dumps(common)
        fp["matching_stratum"] = matching_stratum
        all_fingerprints.append(fp)
        observed.update(region=region, matching_stratum=matching_stratum, common_contexts=len(common), support=common)
        region_results.append(observed)
        region_specs.append((regional, common, fp))
    if not region_specs:
        return pd.DataFrame(), {"status": "insufficient_data", "reason": "need >=2 eligible rosters matched on region/event exposure/series-count band, >=2 series per half, and common context support",
                                "eligible_rosters": len(eligible), "thresholds": {"series": min_series, "events": min_events}}
    weights = np.array([r["n_rosters"] for r in region_results], float)
    effect = float(np.average([r["effect"] for r in region_results], weights=weights))
    null_values = []
    for _ in range(permutations):
        values = [persistence_statistic(fp, features, k, rng.permutation(r["n_rosters"]))["effect"]
                  for (_, _, fp), r in zip(region_specs, region_results)]
        null_values.append(float(np.average(values, weights=weights)))
    series = sorted(valid.series_id.unique())
    bootstrap_values = []
    for _ in range(bootstrap):
        draws = rng.multinomial(len(series), np.full(len(series), 1 / len(series)))
        counts = dict(zip(series, draws))
        values, local_weights = [], []
        for regional, support, original in region_specs:
            fp = standardize_table(regional, features, support, reference, counts)
            try:
                # A replicate that loses a roster/half cannot silently change
                # the target roster population or its weighting.
                original_keys = set(zip(original.roster_id, original.half))
                replicate_keys = set(zip(fp.roster_id, fp.half)) if not fp.empty else set()
                if original_keys != replicate_keys:
                    raise ValueError("bootstrap replicate lost roster/context support")
                result = persistence_statistic(fp, features, k)
                values.append(result["effect"])
                local_weights.append(result["n_rosters"])
            except (ValueError, AttributeError):
                continue
        if len(values) == len(region_specs):
            bootstrap_values.append(float(np.average(values, weights=local_weights)))
    details = {"status": "fit", "effect": effect,
               "within_distance": float(np.average([r["within_distance"] for r in region_results], weights=weights)),
               "different_distance": float(np.average([r["different_distance"] for r in region_results], weights=weights)),
               "p_value": (1 + sum(v >= effect for v in null_values)) / (permutations + 1) if permutations else None,
               "ci_low": float(np.quantile(bootstrap_values, .025)) if bootstrap_values else None,
               "ci_high": float(np.quantile(bootstrap_values, .975)) if bootstrap_values else None,
               "successful_bootstrap": len(bootstrap_values), "permutations": permutations,
               "regions": region_results, "eligible_rosters": len(eligible),
               "thresholds": {"series": min_series, "events": min_events},
               "exchangeability": "Relabel entire B-half roster fingerprints within region, identical event-exposure sets, log2 series-count bands and identical common context support; all series and paired opponents retain their global half. Conditional exchangeability remains an observational assumption.",
               "bootstrap_unit": "complete series across both focal teams; context support and training reference remain frozen"}
    return pd.concat(all_fingerprints, ignore_index=True), details


def player_fingerprints(input_path, split, reference, seed, window_data=None, k=0):
    """Player geometry/role features retain identity; no duplicated team vectors."""
    records = []
    for meta, arrays in iter_compact(input_path, splits={split}):
        if meta.get("split") != split or not meta.get("series_id"):
            continue
        try:
            ids = json.loads(meta["player_ids"]) if isinstance(meta.get("player_ids"), str) else meta.get("player_ids", [])
        except (ValueError, TypeError):
            continue
        if len(ids) < 3:
            continue
        geometry = cover_arrays(arrays)
        frame = pd.DataFrame({"score_diff": arrays["score_diff"], "remaining": arrays["remaining"],
                              "overtime": arrays["overtime"], "ball_y": geometry["ball_y"],
                              "region": meta.get("region") or "unknown"})
        contexts = context_columns(frame).context.to_numpy()
        live = np.asarray(arrays["live"], bool)
        for player in range(3):
            if not ids[player]:
                continue
            valid = live & pd.notna(contexts) & (np.asarray(arrays["roles"])[:, player] >= 0)
            for context in np.unique(contexts[valid]):
                if context not in reference:
                    continue
                sel = valid & (contexts == context)
                ranks = np.asarray(arrays["roles"])[sel, player]
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    cover = float(np.nanmean(geometry["player_cover"][sel, player]))
                    depth = float(np.nanmean(geometry["player_depth"][sel, player])) / 5120
                records.append({"entity_id": ids[player], "series_id": meta["series_id"], "context": context,
                                "half": series_half(meta["series_id"], seed), "role_1": np.mean(ranks == 0),
                                "role_2": np.mean(ranks == 1), "role_3": np.mean(ranks == 2),
                                "player_cover": cover, "player_depth": depth})
    if not records:
        return pd.DataFrame()
    data = pd.DataFrame(records)
    features = ["role_1", "role_2", "role_3", "player_cover", "player_depth"]
    series = data.groupby(["entity_id", "half", "context", "series_id"], observed=True)[features].mean().reset_index()
    contexts = series.groupby(["entity_id", "half", "context"], observed=True)[features].mean().reset_index()
    # A player participates in the team's motifs; these usage coordinates are
    # attributed participation, while roles and cover remain individual traits.
    # Join within context before standardization so the mixture is identical.
    if window_data is not None and not window_data.empty and "player_ids" in window_data:
        token_rows = []
        token_features = [f"token_{i}" for i in range(k)]
        for row in window_data.loc[window_data.context.notna() & window_data.series_id.notna()].to_dict("records"):
            try:
                ids = json.loads(row["player_ids"]) if isinstance(row["player_ids"], str) else row["player_ids"]
            except (TypeError, ValueError):
                continue
            if ids is None:
                continue
            for identity in ids[:3]:
                if identity:
                    token_rows.append({"entity_id": identity, "half": series_half(row["series_id"], seed),
                                       "series_id": row["series_id"], "context": row["context"],
                                       **{name: row[name] for name in token_features}})
        if token_rows:
            token_series = pd.DataFrame(token_rows).groupby(["entity_id", "half", "context", "series_id"], observed=True)[token_features].mean().reset_index()
            token_context = token_series.groupby(["entity_id", "half", "context"], observed=True)[token_features].mean().reset_index()
            contexts = contexts.merge(token_context, on=["entity_id", "half", "context"], how="inner", validate="one_to_one")
            features += token_features
    result = []
    for (entity, half), rows in contexts.groupby(["entity_id", "half"], observed=True):
        rows = rows.dropna(subset=features)
        if rows.empty:
            continue
        weights = rows.context.map(reference).to_numpy(float)
        values = np.average(rows[features].to_numpy(float), axis=0, weights=weights)
        profile = {("team_" + name if name.startswith("token_") else name): value
                   for name, value in zip(features, values)}
        result.append({"entity_type": "player", "entity_id": entity, "half": int(half),
                       "n_contexts": len(rows), "split": split, **profile,
                       "notes": "Individual role/geometry plus participation in team tokens; own supported contexts, no transfer significance claim"})
    return pd.DataFrame(result)


def season_drift(data, features, reference):
    """Frozen-codebook mixture and within-token geometry, descriptive only."""
    records, within = [], []
    valid = data.loc[data.context.isin(reference) & data.series_id.notna()].copy()
    supports = [set(g.context) for _, g in valid.groupby("season", observed=True)]
    common = set.intersection(*supports) if supports else set()
    valid = valid.loc[valid.context.isin(common)]
    for season, rows in valid.groupby("season", observed=True):
        series = rows.groupby(["series_id", "context"], observed=True)[features].mean().reset_index()
        contexts = series.groupby("context")[features].mean()
        weights = np.array([reference[c] for c in contexts.index])
        vals = np.average(contexts.to_numpy(float), axis=0, weights=weights)
        records.append({"entity_type": "season", "entity_id": season, "half": -1,
                        "n_contexts": len(contexts), **dict(zip(features, vals))})
        for token, members in rows.groupby("token", observed=True):
            geometry = members.groupby("series_id")[["third_depth", "coverage", "spacing"]].mean().mean()
            within.append({"season": season, "token": int(token), **geometry.to_dict(),
                           "n_series": int(members.series_id.nunique())})
    return pd.DataFrame(records), within


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--tokens", type=Path)
    parser.add_argument("--split", choices=["val", "test"], default="val")
    parser.add_argument("--min-series", type=int, default=20)
    parser.add_argument("--min-events", type=int, default=3)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args(argv)
    if min(args.min_series, args.min_events) < 1 or min(args.permutations, args.bootstrap) < 0:
        parser.error("eligibility thresholds must be positive; repetitions nonnegative")
    with Run(args, "style", method="Context-standardized independent-series fingerprints") as run:
        _run(args, run)


def _run(args, run):
    run.idea("rq4-persistence", "Roster style persists across series", "running", motivation="Independent-series replication with stable player IDs")
    token_path = args.tokens or args.output / "artifacts" / "tokens" / "windows.parquet"
    folder = args.output / "artifacts" / "style"
    folder.mkdir(parents=True, exist_ok=True)
    if not token_path.exists():
        pd.DataFrame(columns=["entity_type", "entity_id", "half", "split", *feature_columns(args.k)]).to_parquet(folder / "fingerprints.parquet", index=False)
        details = {"status": "insufficient_data", "reason": "No token windows artifact; live-play or training measurement gate failed upstream",
                   "confirmatory": {"rq": "RQ4", "split": args.split, "p_value": None}}
        run.metric(split=args.split, fingerprints=0)
        run.result("style", {"fingerprints": 0}, split=args.split, details=details,
                   notes="No fingerprint evidence is fabricated when the upstream vocabulary is unavailable.")
        run.idea("rq4-persistence", "Roster style persists across series", "pruned", prune_reason=details["reason"])
        update_confirmatory_family(args.output)
        return
    windows = pd.read_parquet(token_path)
    if args.split != "test":
        windows = windows.loc[windows.split != "test"].copy()
    required = {"third_depth", "coverage", "spacing", "ball_y", "score_diff", "remaining", "overtime",
                "region", "series_id", "roster_id", "event", "season", "split", "token"}
    missing = sorted(required - set(windows.columns))
    if missing:
        raise ValueError("token windows missing required style columns: " + ", ".join(missing))
    k = int(windows.k.iloc[0]) if len(windows) and "k" in windows else args.k
    data = window_features(windows, k)
    features = feature_columns(k)
    reference = training_reference(data)
    selected = data.loc[data.split == args.split]
    fingerprints, details = evaluate_persistence(selected, reference, features, k, args.min_series,
                                                  args.min_events, args.permutations, args.bootstrap, args.seed)
    if not fingerprints.empty:
        fingerprints["split"] = args.split
    players = player_fingerprints(args.input, args.split, reference, args.seed, selected, k)
    drift, within = season_drift(data, features, reference)
    frames = [d for d in [fingerprints, players, drift] if not d.empty]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["entity_type", "entity_id", "half", "split", *features])
    combined.to_parquet(folder / "fingerprints.parquet", index=False)
    pd.DataFrame(within, columns=["season", "token", "third_depth", "coverage", "spacing", "n_series"]).to_parquet(folder / "within_token_drift.parquet", index=False)
    sources = set(selected.state_source.fillna("unknown").astype(str)) if "state_source" in selected else {"unknown"}
    vocabulary = read_json(token_path.parent / "vocabulary.json", {})
    state_gate = sources == {"explicit_state_map"}
    vocabulary_gate = bool(vocabulary.get("stable_gate_passed", False))
    inference_gate = state_gate and vocabulary_gate
    details["measurement_gate"] = {"passed": inference_gate, "state_sources": sorted(sources),
                                    "explicit_state_map": state_gate, "stable_vocabulary": vocabulary_gate}
    details["confirmatory"] = {"rq": "RQ4", "split": args.split, "p_value": details.get("p_value") if inference_gate else None}
    details["season_drift"] = {"status": "descriptive", "common_context_standardized": True,
                                "roster_event_composition_adjusted": False,
                                "note": "Calendar drift is not a patch effect; token mixture and within-token geometry saved separately. No out-of-support claim without calibrated vocabulary support."}
    details["identity_policy"] = "Exact stable-player roster IDs; organization identities remain distinct and unavailable organization is not inferred from roster. Player profiles use individual roles and geometry."
    details["training_reference_contexts"] = len(reference)
    metrics = {"fingerprints": len(combined), "player_fingerprints": len(players), "season_fingerprints": len(drift)}
    for key in ("effect", "p_value", "ci_low", "ci_high", "within_distance", "different_distance"):
        if details.get(key) is not None:
            metrics[key] = details[key]
    run.metric(split=args.split, **metrics)
    run.result("style", metrics, split=args.split, details=details,
               notes="Positive persistence effect means different-roster distance exceeds within-roster distance. Roster permutation matches region, event exposure, series-count band and context support.",
               lower_is_better=["p_value"])
    feasible = details["status"] == "fit" and inference_gate
    run.idea("rq4-persistence", "Roster style persists across series", "promising" if feasible else "pruned",
             prune_reason="" if feasible else ("Live-state or vocabulary validation gate failed" if not inference_gate else details.get("reason", "Independent-series common support unavailable")),
             best_metric={"name": "effect", "value": details["effect"], "task": "style", "split": args.split} if feasible else None)
    update_confirmatory_family(args.output)


if __name__ == "__main__":
    main()
