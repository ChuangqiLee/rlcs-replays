"""Matched player retrieval with paired observed-series bootstrap intervals.

Every representation is indexed by the same, unmodified player-game table.
Eligibility, candidate masks and bootstrap draws are constructed once.  No
2025 value fits an imputer, a metric scale, or a representation transform.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from tactics_code.style_retrieval import (
    check_rows, context_maps, eligible_players, identity_regions, metric_scores,
)

METRICS = ("top1", "top5", "mrr")
GAME_KEYS = ("identity_id", "season", "replay_id")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def train_standardize(values, train_mask, *, center=True, scale=True):
    """Impute/transform all games using ALL usable training games only."""
    values = np.asarray(values, dtype=np.float64)
    train_mask = np.asarray(train_mask, dtype=bool)
    if values.ndim != 2 or train_mask.shape != (len(values),) or not train_mask.any():
        raise ValueError("Need a game-by-feature matrix and nonempty training mask")
    train = values[train_mask]
    finite = np.isfinite(train)
    count = finite.sum(axis=0)
    mean = np.divide(np.where(finite, train, 0).sum(axis=0), count,
                     out=np.zeros(values.shape[1]), where=count > 0)
    imputed = np.where(finite, train, mean)
    std = imputed.std(axis=0)
    std[std < 1e-10] = 1.
    result = np.where(np.isfinite(values), values, mean)
    if center:
        result = result - mean
    if scale:
        result = result / std
    return result, {"fit_split": "train", "mean": mean.tolist(),
                    "scale": std.tolist(), "center_applied": center,
                    "scale_applied": scale,
                    "all_missing_feature_indices": np.flatnonzero(count == 0).tolist()}


def _unit(values):
    norm = np.linalg.norm(values, axis=1, keepdims=True)
    if not np.isfinite(values).all() or np.any(norm <= 1e-12):
        raise ValueError("Cosine retrieval requires finite, nonzero aggregate vectors")
    return values / norm


def _distance(query, gallery, metric):
    if metric == "cosine":
        return np.clip(1 - np.einsum("ij,kj->ik", _unit(query), _unit(gallery),
                                    optimize=False), 0., 2.)
    if metric == "euclidean":
        # Squared Euclidean has the same ranking; subtraction avoids cancellation.
        return np.asarray([np.sum((gallery - row)**2, axis=1) for row in query])
    raise ValueError("metric must be cosine or euclidean")


def _train_distance_scale(gallery, metric):
    """Mean off-diagonal distance over ALL train identity means, in O(ND)."""
    if len(gallery) < 2:
        raise ValueError("Distance scaling needs two training identities")
    n = len(gallery)
    if metric == "cosine":
        unit = _unit(gallery)
        value = n / (n - 1) * max(0., 1. - float(np.sum(unit.mean(axis=0)**2)))
    else:
        value = 2 * n / (n - 1) * float(np.sum(gallery.var(axis=0)))
    return max(value, 1e-12), value <= 1e-12


def _population(games, metadata):
    check_rows(games)
    if games.empty or games.duplicated(list(GAME_KEYS)).any():
        raise ValueError("Need nonempty, unique player-games for the shared benchmark")
    if games[list(GAME_KEYS) + ["series_id", "roster_id"]].isna().any().any():
        raise ValueError("Player-game, series and roster keys must be known")
    check_rows(pd.DataFrame(metadata))
    train, val = games[games.split == "train"], games[games.split == "val"]
    if set(train.replay_id) & set(val.replay_id):
        raise ValueError("Replay appears in both training and 2025")
    if set(train.series_id) & set(val.series_id):
        raise ValueError("Observed series appears in both training and 2025")
    eligible = eligible_players(train, val)
    regions = identity_regions(metadata)
    ids = [identity for identity in eligible if identity in regions]
    report = {"eligible_before_region": len(eligible),
              "excluded_unknown_train_region": len(eligible) - len(ids),
              "n_gallery": len(ids), "eligible_ids": ids,
              "player_games": len(games), "minimum_games_per_individual_season": 20,
              "game_keys_sha256": _digest(games[list(GAME_KEYS)].values.tolist())}
    if len(ids) < 2:
        return report, None
    query_games = val[val.identity_id.isin(ids)]
    grouped = query_games.groupby(["identity_id", "series_id"], sort=True)
    keys = list(grouped.groups)
    query_rosters = grouped.roster_id.agg(set).to_list()
    rosters, teammates = context_maps(metadata)
    allowed = np.array([[not (rosters[p] & query_rosters[i]) and p not in teammates[identity]
                         for p in ids] for i, (identity, _) in enumerate(keys)], dtype=bool)
    target = np.array([ids.index(identity) for identity, _ in keys], dtype=np.int64)
    report.update(query_keys_sha256=_digest(keys),
                  gallery_sha256=_digest(ids),
                  population_sha256=_digest({"gallery": ids, "queries": keys,
                                             "games": games[list(GAME_KEYS)].values.tolist()}),
                  team_candidate_mask_sha256=_digest(allowed.tolist()),
                  query_keys=[list(key) for key in keys],
                  train_region_strata={p: regions[p] for p in ids})
    return report, (ids, keys, target, allowed)


def _analysis(distances, baseline, target, masks, keys, bootstrap, seed):
    keep = masks[np.arange(len(target)), target] & (masks.sum(axis=1) >= 2)
    report = {"queries_total": len(target), "queries_evaluated": int(keep.sum()),
              "excluded_true_identity": int((~masks[np.arange(len(target)), target]).sum()),
              "excluded_fewer_than_two_candidates": int((masks.sum(axis=1) < 2).sum()),
              "bootstrap": bootstrap, "bootstrap_seed": seed + 1,
              "bootstrap_unit": "complete observed 2025 series, conditional on fitted gallery/model"}
    if not keep.any():
        return {**report, "status": "insufficient_data", "methods": {}}
    names = list(distances)
    scores = np.stack([metric_scores(distances[name][keep], target[keep], masks[keep])
                       for name in names])
    series = np.asarray([key[1] for key in keys], dtype=str)[keep]
    series_ids, inverse = np.unique(series, return_inverse=True)
    n_series = len(series_ids)
    sums = np.zeros((n_series, len(names), len(METRICS)))
    np.add.at(sums, inverse, scores.transpose(1, 0, 2))
    counts = np.bincount(inverse, minlength=n_series)
    draws = np.empty((bootstrap, len(names), len(METRICS)))
    rng = np.random.default_rng(seed + 1)
    for b in range(bootstrap):
        weights = np.bincount(rng.integers(n_series, size=n_series), minlength=n_series)
        draws[b] = np.einsum("s,smk->mk", weights, sums) / (weights @ counts)
    base_index = names.index(baseline)
    point = scores.mean(axis=1)
    selected_keys = [keys[i] for i in np.flatnonzero(keep)]
    results = {}
    for i, name in enumerate(names):
        metrics, differences = {}, {}
        for j, metric in enumerate(METRICS):
            metrics[metric] = {"estimate": float(point[i, j]),
                               "ci95": np.quantile(draws[:, i, j], [.025, .975]).tolist()
                               if bootstrap else [None, None]}
            differences[metric] = {
                "estimate": float(point[i, j] - point[base_index, j]),
                "ci95": np.quantile(draws[:, i, j] - draws[:, base_index, j],
                                     [.025, .975]).tolist() if bootstrap else [None, None]}
        results[name] = {"metrics": metrics, "paired_difference_vs_baseline": differences,
                         "per_query": [{"identity_id": identity, "series_id": series_id,
                                        **dict(zip(METRICS, scores[i, q].tolist()))}
                                       for q, (identity, series_id) in enumerate(selected_keys)]}
    sizes = masks[keep].sum(axis=1)
    harmonic = np.r_[0., np.cumsum(1 / np.arange(1, masks.shape[1] + 1))]
    return {**report, "status": "fit", "methods": results, "n_series": n_series,
            "series_ids": series_ids.tolist(), "series_query_counts": counts.tolist(),
            "candidate_count": {"min": int(sizes.min()), "median": float(np.median(sizes)),
                                "max": int(sizes.max())},
            "chance": dict(zip(METRICS, [float(np.mean(1 / sizes)),
                                        float(np.mean(np.minimum(5, sizes) / sizes)),
                                        float(np.mean(harmonic[sizes] / sizes))]))}


def evaluate_methods(games, metadata, methods, *, baseline="handcrafted", bootstrap=2000, seed=42):
    """Evaluate game-aligned methods with paired CIs on one fixed population.

    A method is an N x D matrix (finite embeddings; cosine default), or a dict
    with ``values``, ``metric``, ``standardize`` and/or ``center``.  Standardize
    uses train-game mean imputation/centering/SD; center only uses train means.
    A fusion dict has ``components`` naming previous methods and optional
    nonnegative ``weights`` (default equal); each component distance is divided
    by its mean off-diagonal distance over ALL train identity means first.
    """
    if baseline not in methods or bootstrap < 0 or int(bootstrap) != bootstrap:
        raise ValueError("Need named baseline and nonnegative integer bootstrap count")
    bootstrap = int(bootstrap)
    games = games.reset_index(drop=True).copy()
    population, layout = _population(games, metadata)
    report = {"population": population, "baseline": baseline,
              "test_opened": False, "evaluation_season": "rlcs-2025",
              "historical_top1_reference": {"estimate": .15392, "gallery": 112, "queries": 1007,
                  "use": "historical context only; inference uses freshly recomputed same-cohort baseline"},
              "bootstrap_seed": seed + 1, "methods": {}}
    if layout is None:
        return {**report, "status": "insufficient_data",
                "reason": "Fixed 20-game individual-season gate and train-region rule leave <2 players"}
    ids, keys, target, allowed = layout
    train_mask = games.split.eq("train").to_numpy()
    train_rows = games.loc[train_mask]
    val_rows = games.loc[~train_mask & games.identity_id.isin(ids)]
    distances, distance_scales = {}, {}
    for name, supplied in methods.items():
        spec = supplied if isinstance(supplied, dict) else {"values": supplied}
        if "components" in spec:
            components = list(spec["components"])
            weights = np.asarray(spec.get("weights", [1.] * len(components)), dtype=float)
            if (not components or len(set(components)) != len(components)
                    or any(c not in distances for c in components)
                    or weights.shape != (len(components),) or not np.isfinite(weights).all()
                    or np.any(weights < 0) or weights.sum() <= 0):
                raise ValueError("Fusion needs distinct preceding methods and finite nonnegative weights")
            weights /= weights.sum()
            distances[name] = sum(w * distances[c] / distance_scales[c]
                                  for w, c in zip(weights, components))
            distance_scales[name] = 1.
            report["methods"][name] = {"metric": "train-distance-scaled late fusion",
                                       "components": components, "weights": weights.tolist(),
                                       "component_scales": {c: distance_scales[c] for c in components}}
            continue
        values = np.asarray(spec["values"], dtype=np.float64)
        if values.ndim != 2 or len(values) != len(games) or values.shape[1] == 0:
            raise ValueError(f"Method {name} must provide exactly one nonempty vector per shared game")
        metric = spec.get("metric", "cosine")
        standardize = bool(spec.get("standardize", False))
        center = standardize or bool(spec.get("center", False))
        scaling = None
        if center or standardize:
            values, scaling = train_standardize(values, train_mask, center=center, scale=standardize)
        elif not np.isfinite(values).all():
            raise ValueError(f"Method {name} contains nonfinite embeddings")
        columns = [f"v_{i}" for i in range(values.shape[1])]
        vectors = pd.DataFrame(values, columns=columns)
        all_gallery = vectors.loc[train_rows.index].groupby(train_rows.identity_id, sort=True).mean()
        gallery = all_gallery.loc[ids].to_numpy()
        query = vectors.loc[val_rows.index].groupby([val_rows.identity_id, val_rows.series_id],
                                                   sort=True).mean()
        if list(query.index) != keys:
            raise AssertionError("Method query population drifted")
        distances[name] = _distance(query.to_numpy(), gallery, metric)
        if not np.isfinite(distances[name]).all():
            raise ValueError(f"Method {name} produced nonfinite distances")
        distance_scales[name], floored = _train_distance_scale(all_gallery.to_numpy(), metric)
        report["methods"][name] = {"metric": metric, "dimension": values.shape[1],
                                   "scaling": scaling, "train_distance_scale": distance_scales[name],
                                   "train_distance_scale_floored": floored,
                                   "aggregation": "equal games per gallery identity and player-series query"}
    report.update(status="fit",
                  primary=_analysis(distances, baseline, target, np.ones_like(allowed), keys, bootstrap, seed),
                  team_context_control=_analysis(distances, baseline, target, allowed, keys, bootstrap, seed))
    return report
