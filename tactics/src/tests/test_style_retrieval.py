"""Synthetic retrieval controls and guards; these tests never open RLCS data."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from tactics_code.style_retrieval import (
    bootstrap_series_weights,
    evaluate_retrieval,
    fit_gallery,
    segment_features,
    shuffle_query_labels,
)


def synthetic_features(n_identities=20, n_series=8, *, null=False, seed=6):
    """Independent train/val bouts; balanced null has exactly known chance."""
    rng = np.random.default_rng(seed)
    features = [f"f_{j}" for j in range(n_identities)]
    prototypes = np.eye(n_identities) * 4
    frames = []
    for split, season in (("train", "rlcs-2024"), ("val", "rlcs-2025")):
        records = []
        count = n_identities if null and split == "val" else n_series
        for series in range(count):
            for identity in range(n_identities):
                source = (identity + series) % n_identities if null and split == "val" else identity
                values = prototypes[source].copy()
                if not null:
                    values += rng.normal(0, .015, size=n_identities)
                for segment in range(2):
                    records.append({
                        "identity_id": f"p{identity:02d}", "region": "EU", "season": season,
                        "split": split, "series_id": f"{split}-s{series}",
                        "replay_id": f"{split}-s{series}-game", "segment_id": segment,
                        **dict(zip(features, values)),
                    })
        frames.append(pd.DataFrame(records))
    return frames[0], frames[1], features


def test_planted_cross_season_identity_recovered():
    train, val, features = synthetic_features()
    result = evaluate_retrieval(train, val, features, permutations=199, bootstrap=99, seed=42)
    assert result["status"] == "fit"
    for metric in ("top1", "top5", "mrr"):
        assert result["metrics"][metric] > .98
        assert result["details"]["metrics"][metric]["p_value"] <= .02
        interval = result["details"]["metrics"][metric]
        assert interval["ci_low"] <= result["metrics"][metric] <= interval["ci_high"]
    assert result["details"]["successful_bootstrap"] == 99
    assert abs(result["details"]["metrics"]["top1"]["null_mean"] - .05) < .025
    assert abs(result["details"]["metrics"]["top5"]["null_mean"] - .25) < .04


def test_balanced_identity_independent_null_is_exact_chance():
    train, val, features = synthetic_features(null=True)
    result = evaluate_retrieval(train, val, features, permutations=49, bootstrap=39, seed=7)
    chance = {"top1": 1 / 20, "top5": 5 / 20,
              "mrr": sum(1 / rank for rank in range(1, 21)) / 20}
    for metric, target in chance.items():
        assert result["metrics"][metric] == pytest.approx(target, abs=1e-12)
        details = result["details"]["metrics"][metric]
        assert details["null_mean"] == pytest.approx(target, abs=1e-12)
        assert details["p_value"] > .05
        assert result["details"]["chance"][metric] == pytest.approx(target)


def test_permutation_moves_whole_identity_within_region_season():
    _, val, features = synthetic_features()
    second = val.copy()
    second["region"] = "NA"
    second["identity_id"] = "na-" + second["identity_id"]
    second["series_id"] = "na-" + second["series_id"]
    original = pd.concat([val, second], ignore_index=True)
    permuted = shuffle_query_labels(original, np.random.default_rng(123))
    assert len(permuted) == len(original)
    pd.testing.assert_frame_equal(permuted.drop(columns="identity_id"), original.drop(columns="identity_id"))
    paired = original[["region", "season", "identity_id"]].copy()
    paired["permuted"] = permuted["identity_id"].to_numpy()
    assert (paired.groupby(["region", "season", "identity_id"]).permuted.nunique() == 1).all()
    for keys, group in paired.groupby(["region", "season"]):
        assert set(group.identity_id) == set(group.permuted)
    assert (paired.identity_id != paired.permuted).any()


def test_bootstrap_resamples_complete_global_series():
    _, val, _ = synthetic_features()
    weights = bootstrap_series_weights(val, np.random.default_rng(9))
    assert set(weights) == set(val.series_id.unique())
    assert sum(weights.values()) == val.series_id.nunique()
    assert all(isinstance(value, (int, np.integer)) and value >= 0 for value in weights.values())
    # Both sides/all identities and both segments of a series share its one draw.
    applied = val.series_id.map(weights)
    assert applied.notna().all()
    assert (applied.groupby(val.series_id).nunique() == 1).all()
    # Duplicating within-series observations cannot change a cluster draw.
    duplicated = pd.concat([val, val.iloc[:37]], ignore_index=True)
    assert weights == bootstrap_series_weights(duplicated, np.random.default_rng(9))


def test_fitted_gallery_is_train_only_and_equal_series_weighted():
    train, val, features = synthetic_features()
    original = train.copy(deep=True)
    model = fit_gallery(train, features)
    assert set(model["galleries"]) == {"EU"}
    assert len(model["galleries"]["EU"]["ids"]) == 20
    contaminated_val = val.copy()
    contaminated_val[features] += 1e9
    evaluate_retrieval(train, contaminated_val, features, permutations=0, bootstrap=0, seed=42)
    pd.testing.assert_frame_equal(train, original)
    refit = fit_gallery(train, features)
    np.testing.assert_array_equal(model["mean"], refit["mean"])
    np.testing.assert_array_equal(model["scale"], refit["scale"])
    np.testing.assert_array_equal(model["galleries"]["EU"]["vectors"], refit["galleries"]["EU"]["vectors"])
    # Duplicated segments in an existing replay must not give its series extra weight.
    duplicated = pd.concat([train, train[train.series_id == "train-s0"]] * 2, ignore_index=True)
    repeated = fit_gallery(duplicated, features)
    np.testing.assert_allclose(model["mean"], repeated["mean"], atol=1e-12)
    np.testing.assert_allclose(model["galleries"]["EU"]["vectors"], repeated["galleries"]["EU"]["vectors"], atol=1e-12)


def array_fixture(n=600):
    time = np.arange(n, dtype=float) / 10
    players = np.zeros((n, 6, 8), dtype=float)
    players[:, :3, :3] = [[-1100, -1800, 17], [700, 900, 100], [2300, -700, 300]]
    players[:, :, 3:6] = [700, 1100, 50]
    players[:, :, 6] = 100
    players[:, :, 7] = np.nan  # unknown demolition is not a fabricated absence.
    players[:, :3, 1] += np.sin(time[:, None]) * 20
    flags = np.zeros((n, 6, 4), float)
    flags[::11, 0, 0] = 1
    flags[::7, 1, 1] = 1
    touch = np.full(n, -1, dtype=int)
    touch[::37] = 0
    return {"time": time, "frame": np.arange(n) * 3, "live": np.ones(n, bool),
            "segment": np.zeros(n, int), "players": players,
            "ball": np.tile([0, 100, 100, 250, 500, 10], (n, 1)),
            "flags": flags, "roles": np.tile([0, 1, 2], (n, 1)),
            "role_uncertain": np.zeros(n, bool), "touch": touch,
            "remaining": 300 - time, "score_diff": np.zeros(n), "overtime": np.zeros(n)}


def metadata_fixture():
    return {"replay_id": "r", "series_id": "s", "season": "rlcs-2025", "split": "val",
            "region": "EU", "focal_team": 0, "player_ids": ["p0", "p1", "p2"],
            "player_names": ["zero", "one", "two"], "roster_id": "roster:r",
            "org_id": "org:o", "fps": 10.}


def test_team_features_are_player_slot_invariant():
    arrays, metadata = array_fixture(), metadata_fixture()
    baseline = segment_features(metadata, arrays, "roster")
    assert baseline
    order = np.array([2, 0, 1, 3, 4, 5])
    permuted = deepcopy(arrays)
    permuted["players"] = arrays["players"][:, order]
    permuted["flags"] = arrays["flags"][:, order]
    permuted["roles"] = arrays["roles"][:, order[:3]]
    valid_touch = arrays["touch"] >= 0
    permuted["touch"][valid_touch] = np.argsort(order)[arrays["touch"][valid_touch]]
    changed_metadata = dict(metadata, player_ids=[metadata["player_ids"][i] for i in order[:3]])
    changed = segment_features(changed_metadata, permuted, "roster")
    assert len(baseline) == len(changed)
    for old, new in zip(baseline, changed):
        features = sorted(key for key in old if key.startswith("f_"))
        assert features
        np.testing.assert_allclose([old[key] for key in features], [new[key] for key in features],
                                   atol=1e-12, equal_nan=True)


def test_short_live_bouts_are_not_bridged_across_segment_boundaries():
    arrays = array_fixture(240)
    arrays["segment"] = np.repeat(np.arange(3), 80)  # three separate eight-second bouts
    assert segment_features(metadata_fixture(), arrays, "player", min_seconds=10.) == []
    arrays["segment"][:] = 0
    assert len(segment_features(metadata_fixture(), arrays, "player", min_seconds=10.)) == 3


def test_train_validation_boundaries_reject_heldout_2026():
    train, val, features = synthetic_features()
    invalid = train.copy()
    invalid.loc[0, "season"] = "rlcs-2026"
    invalid.loc[0, "split"] = "test"
    with pytest.raises(ValueError, match="2026|season|train|test"):
        fit_gallery(invalid, features)
    invalid = val.copy()
    invalid.loc[0, "season"] = "rlcs-2026"
    with pytest.raises(ValueError, match="2026|season|val|test"):
        evaluate_retrieval(train, invalid, features, permutations=0, bootstrap=0)
