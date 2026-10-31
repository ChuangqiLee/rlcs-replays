"""Corrected pressure responses are additive, series-clustered and observational."""
import numpy as np
import pandas as pd

from tactics_code.pressure import (CORRECTED_MEASURES, MEASURES, cover_arrays,
                                   fit_pressure, last_man_arrays,
                                   series_context_summary, summarize_replay)


def _compact(n=8):
    players = np.zeros((n, 6, 8))
    players[:, :, 6] = 50
    players[:, :3, 1] = [-2500, -500, 1500]
    players[:, 3:, 1] = [-1200, 500, 2200]
    ball = np.zeros((n, 6))
    ball[:, 1] = 600
    return {"players": players, "ball": ball,
            "roles": np.tile([2, 1, 0], (n, 1)), "live": np.ones(n, bool),
            "remaining": np.full(n, 30.), "overtime": np.zeros(n),
            "score_diff": np.full(n, -1.)}


def _meta():
    return dict(replay_id="synthetic", series_id="series-0", season="rlcs-2025",
                split="val", roster_id="roster", team_id="team", event="event",
                region="EU", focal_team=0)


def test_corrected_pressure_metric_masks_and_sign():
    arrays = _compact()
    arrays["players"][1, 0, 1] += 400
    arrays["players"][2, 1, 7] = 1  # Known demolition invalidates deepest line.
    arrays["players"][3, 2, 0] = np.nan
    arrays["role_uncertain"] = np.ones(8, bool)
    metrics = last_man_arrays(arrays)
    assert metrics["last_man_y_own"][0] == 2620
    assert metrics["last_man_behind_ball"][0] == 3100
    assert metrics["last_man_y_own"][1] - metrics["last_man_y_own"][0] == 400
    assert metrics["last_man_behind_ball"][1] - metrics["last_man_behind_ball"][0] == -400
    assert np.isnan(metrics["last_man_y_own"][[2, 3]]).all()
    # Role uncertainty belongs to the original proximity role only.
    assert np.isnan(cover_arrays(arrays)["third_depth"]).all()
    assert np.isfinite(metrics["last_man_y_own"][[0, 1, 4, 5, 6, 7]]).all()


def test_corrected_pressure_summaries_keep_historical_measures():
    arrays = _compact()
    arrays["players"][2, 1, 7] = 1
    arrays["players"][3, 2, 0] = np.nan
    rows = pd.DataFrame(summarize_replay(_meta(), arrays))
    summary = series_context_summary(rows)
    legacy_rows = rows.drop(columns=[key + suffix for key in CORRECTED_MEASURES
                                    for suffix in ("", "_n")])
    legacy = series_context_summary(legacy_rows)
    pd.testing.assert_frame_equal(summary[legacy.columns], legacy)
    assert set(MEASURES).isdisjoint(CORRECTED_MEASURES)
    for name in CORRECTED_MEASURES:
        assert summary[name + "_n"].iloc[0] == 6
    original = cover_arrays(arrays)
    for name in MEASURES:
        np.testing.assert_allclose(rows[name].iloc[0], np.nanmean(original[name]))


def _pressure_panel():
    rows = []
    rng = np.random.default_rng(931)
    for series in range(12):
        # The same independent-series offset is present in all four cells.
        offset = rng.normal(0, 20)
        for late in (0, 1):
            for score in (-1, 1):
                interaction = late * (score < 0)
                row = dict(split="val", series_id=f"s{series}", overtime=0,
                           score_diff=score, remaining=30 if late else 120,
                           late=late, season="rlcs-2025", region="EU", roster_id="roster",
                           ball_x=0., ball_y=0., ball_z=100., ball_speed=1000., mean_boost=50.,
                           uncovered=.25 + .03 * interaction + offset / 10000,
                           third_depth=1400 - 120 * interaction + offset,
                           coverage=1.2 - .04 * interaction + offset / 1000,
                           spacing=1500 + 80 * interaction + offset,
                           last_man_y_own=2300 + 500 * interaction + offset,
                           last_man_behind_ball=2820 - 500 * interaction - offset)
                rows.append(row)
    return pd.DataFrame(rows)


def test_corrected_pressure_known_interaction_and_legacy_models_unchanged():
    panel = _pressure_panel()
    result = fit_pressure(panel, n_bootstrap=49, regression="ols")
    legacy = fit_pressure(panel.drop(columns=CORRECTED_MEASURES), n_bootstrap=49,
                          regression="ols")
    assert result["models"] == legacy["models"]
    assert set(result["models"]) == {"uncovered", "third_depth", "coverage", "spacing"}
    for name, expected in (("last_man_y_own", 500), ("last_man_behind_ball", -500)):
        model = result["corrected_models"][name]
        assert model["status"] == "fit"
        assert model["n_series"] == 12
        np.testing.assert_allclose(model["estimate"], expected, atol=1e-8)
        assert model["series_bootstrap"]["successful_replicates"] == 49
        np.testing.assert_allclose([model["series_bootstrap"]["ci_low"],
                                   model["series_bootstrap"]["ci_high"]], expected, atol=1e-8)
        assert legacy["corrected_models"][name]["status"] == "unavailable"


def test_corrected_pressure_reports_failed_support():
    panel = _pressure_panel()
    panel = panel.loc[panel.series_id.isin(["s0", "s1"])]
    result = fit_pressure(panel, n_bootstrap=0, regression="ols")
    assert result["models"] == {}
    assert result["status"] == "insufficient_data"
    assert set(result["corrected_models"]) == set(CORRECTED_MEASURES)
    assert all(model["status"] == "insufficient_data"
               for model in result["corrected_models"].values())
