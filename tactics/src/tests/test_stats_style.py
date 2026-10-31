import json

import numpy as np
import pandas as pd
import pytest

from tactics_code.pressure import cover_arrays, fit_pressure, summarize_replay
from tactics_code.stats import adjust_pvalues, bootstrap_ols, cluster_ols, update_confirmatory_family
from tactics_code.style import (context_columns, evaluate_persistence, feature_columns,
                                persistence_statistic, series_half, window_features)


def geometric_fixture():
    players = np.zeros((4, 6, 8), float)
    players[:, :3, :3] = [[0, -1000, 17], [3000, -1000, 17], [0, 1000, 17]]
    ball = np.tile([0, 0, 100, 10, 20, 0], (4, 1)).astype(float)
    return {"players": players, "ball": ball, "roles": np.tile([0, 1, 2], (4, 1)),
            "role_uncertain": np.zeros(4, bool)}


def test_planar_cover_and_missingness():
    arrays = geometric_fixture()
    geometry = cover_arrays(arrays)
    np.testing.assert_allclose(geometry["coverage"], 1)
    np.testing.assert_allclose(geometry["third_depth"], -1000)
    assert not geometry["uncovered"].any()
    arrays["ball"][0, :2] = [0, -5120]  # degenerate goal/ball segment
    arrays["players"][1, 1, :3] = np.nan  # parser missingness is not zero cover
    arrays["players"][2, 1, :3] = np.nan
    arrays["players"][2, 1, 7] = 1  # known demolition is known absence
    arrays["role_uncertain"][3] = True
    geometry = cover_arrays(arrays)
    assert np.isnan(geometry["coverage"][0])
    assert np.isnan(geometry["coverage"][1])
    assert geometry["coverage"][2] == 1
    assert np.isnan(geometry["third_depth"][3])


def test_cover_left_right_invariant_and_player_permutation_equivariant():
    original = geometric_fixture()
    changed = {k: v.copy() for k, v in original.items()}
    changed["players"][:, :, [0, 3]] *= -1
    changed["ball"][:, [0, 3]] *= -1
    changed["players"][:, :3] = changed["players"][:, [2, 0, 1]]
    changed["roles"] = changed["roles"][:, [2, 0, 1]]
    a, b = cover_arrays(original), cover_arrays(changed)
    for key in ("coverage", "third_depth", "spacing", "uncovered"):
        np.testing.assert_allclose(a[key], b[key])


def test_multiplicity_missing_keeps_family_slot(tmp_path):
    assert adjust_pvalues([.01, None, .04], "holm") == [.03, None, .08]
    np.testing.assert_allclose(adjust_pvalues([.01, .04, .03], "bh"), [.03, .04, .04])
    folder = tmp_path / "results"
    folder.mkdir()
    for rq, p in [("RQ1", .01), ("RQ3", .04)]:
        (folder / f"{rq}.json").write_text(json.dumps({"is_baseline": False, "split": "test",
            "details": {"confirmatory": {"rq": rq, "p_value": p, "split": "test"}}}))
    results = update_confirmatory_family(tmp_path)
    result = next(r for r in results if r["split"] == "test")
    assert result["metrics"]["RQ1_p_holm"] == .03
    assert result["metrics"]["RQ3_p_holm"] == .08
    assert result["details"]["tests"][2]["p_holm"] is None


def test_cluster_ols_and_whole_series_bootstrap():
    rng = np.random.default_rng(4)
    groups = np.repeat(np.arange(24), 20)
    predictor = rng.normal(size=len(groups))
    response = 1 + 2 * predictor + np.repeat(rng.normal(size=24), 20) + rng.normal(size=len(groups)) * .1
    x = np.column_stack([np.ones(len(groups)), predictor])
    fit = cluster_ols(x, response, groups)
    assert abs(fit["beta"][1] - 2) < .1
    assert fit["n_series"] == 24
    interval = bootstrap_ols(x, response, groups, 1, 40, 4)
    assert interval["successful_replicates"] == 40
    assert interval["ci_low"] < fit["beta"][1] < interval["ci_high"]
    with pytest.raises(ValueError):
        cluster_ols(np.ones((10, 2)), np.ones(10), np.repeat([0, 1], 5))


def test_pressure_no_context_is_explicit():
    empty = pd.DataFrame(columns=["split", "series_id", "overtime", "score_diff", "remaining"])
    result = fit_pressure(empty, n_bootstrap=3)
    assert result["status"] == "insufficient_data"
    assert result["models"] == {}


def test_zero_second_is_not_pooled_with_late_positive_clock():
    arrays = geometric_fixture()
    arrays.update(live=np.ones(4, bool), score_diff=np.ones(4), remaining=np.array([0., 0., 2., 3.]),
                  overtime=np.zeros(4))
    rows = summarize_replay({"replay_id": "r", "focal_team": 0}, arrays)
    assert len(rows) == 2
    assert {row["zero_second"] for row in rows} == {False, True}
    assert next(row for row in rows if not row["zero_second"])["remaining"] == 2.5


def test_pressure_interaction_known_effect_uses_series_not_frames(monkeypatch):
    rng = np.random.default_rng(13)
    records = []
    for series in range(24):
        intercept = rng.normal(scale=.01)
        for late in (0, 1):
            for score in (-1, 1):
                response = .2 + .1 * late + .04 * (score == -1) + .15 * late * (score == -1) + intercept + rng.normal(scale=.01)
                records.append({"split": "val", "series_id": f"s{series}", "roster_id": f"r{series % 4}",
                                "region": "EU", "season": "rlcs-2025", "overtime": 0., "score_diff": score,
                                "remaining": 40. if late else 120., "late": late, "uncovered": response,
                                "third_depth": 1000 * response, "coverage": 2 - response, "spacing": 2000 * response,
                                "ball_x": 0., "ball_y": 0., "ball_z": 100., "ball_speed": 100., "mean_boost": 50.})
    result = fit_pressure(pd.DataFrame(records), n_bootstrap=29, regression="ols")
    assert result["status"] == "fit"
    primary = result["models"]["uncovered"]
    assert abs(primary["estimate"] - .15) < .02
    assert primary["n_series"] == 24
    assert primary["p_value"] < .01
    assert primary["series_bootstrap"]["successful_replicates"] == 29
    monkeypatch.setattr("tactics_code.pressure.mixed_effect_sensitivity", lambda *args, **kwargs:
                        {"status": "fit", "method": "mock crossed mixed effects", "estimate": .11,
                         "se": .02, "p_value": .03, "ci_low": .07, "ci_high": .15})
    auto = fit_pressure(pd.DataFrame(records), n_bootstrap=9, regression="auto")["models"]["uncovered"]
    assert auto["estimate"] == .11
    assert auto["p_value"] == .03
    assert auto["ci_low"] == .07
    assert auto["method"] == "mock crossed mixed effects"
    assert "series_bootstrap" not in auto
    assert abs(auto["ols_sensitivity"]["estimate"] - .15) < .02
    assert auto["ols_sensitivity"]["series_bootstrap"]["successful_replicates"] == 9


def test_global_series_halves_and_unknown_context():
    assert series_half("same-series", 12) == series_half("same-series", 12)
    known = pd.DataFrame({"score_diff": [0., np.nan], "remaining": [45., 45.],
                          "overtime": [0., 0.], "ball_y": [0., 0.], "region": ["EU", "EU"]})
    assert context_columns(known).context.notna().tolist() == [True, False]


def test_context_standardized_persistence_and_permutation():
    rows = []
    for roster in range(4):
        for series in range(24):
            rows.append({"roster_id": f"r{roster}", "series_id": f"s{roster}-{series}",
                         "event": f"e{series % 3}", "region": "EU", "season": "rlcs-2025",
                         "split": "val", "token": roster, "score_diff": 0, "remaining": 45,
                         "overtime": 0, "ball_y": 0, "third_depth": 1000 + roster * 200,
                         "coverage": 1, "spacing": 2000})
    data = window_features(pd.DataFrame(rows), 4)
    features = feature_columns(4)
    reference = {data.context.iloc[0]: 1.}
    fingerprints, result = evaluate_persistence(data, reference, features, 4, 20, 3, 40, 10, 42)
    assert result["status"] == "fit"
    assert result["effect"] > .8
    assert result["within_distance"] < 1e-10
    assert result["p_value"] < .2
    assert result["successful_bootstrap"] == 10
    assert len(fingerprints) == 8
    swapped = persistence_statistic(fingerprints, features, 4, np.array([1, 0, 3, 2]))
    assert swapped["effect"] < result["effect"]
    fingerprints, insufficient = evaluate_persistence(data, reference, features, 4, 100, 3, 2, 2)
    assert insufficient["status"] == "insufficient_data"
    assert fingerprints.empty
