"""Deterministic synthetic tests; no real replay arrays or network access."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from tactics_code import rotation_latency as rl
from tactics_code.common import atomic_json

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / 'artifacts'


def simple_arrays():
    t = np.arange(0., 13., .5)
    n = len(t)
    p = np.zeros((n, 6, 8))
    p[:, :, 6] = 50.
    p[:, 0, 1] = np.where(t < 3., 0., rl.GOAL_Y + 1000.)
    b = np.zeros((n, 6))
    b[:, 1] = 2000.
    touch = np.full(n, -1)
    touch[0], touch[2] = 0, 3
    return dict(time=t, players=p, ball=b, touch=touch, live=np.ones(n),
                segment=np.zeros(n), remaining=np.full(n, 45.), score_diff=np.full(n, -1.),
                overtime=np.zeros(n))


def meta(team=0):
    return dict(series_id='series', replay_id='replay', season=rl.VAL_SEASON,
                split='val', focal_team=team, fps=2., state_source='explicit_state_map')


def event_tables():
    goals = pd.DataFrame(columns=['replay_id', 'series_id', 'season', 'validated',
                                  'scoring_team', 'time', 'last_live_time'])
    replay = dict(replay_id='replay', series_id='series', season=rl.VAL_SEASON, validated=True,
                  observed_start_time=0., observed_end_time=20., terminal_time=np.nan,
                  terminal_verified=False, gap_start_times='[]', gap_end_times='[]')
    return goals, replay


def extract(a=None, team=0):
    goals, replay = event_tables()
    records, audit = rl.replay_losses(meta(team), simple_arrays() if a is None else a, goals, replay)
    return pd.DataFrame(records), audit


def write_fixture(root, n_series=32):
    """Paired canonical solver fixture, not a physical match simulation."""
    root = Path(root)
    directory = root / rl.VAL_SEASON
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(rl.SEED)
    blocks, metadata, goals, replays = [], [], [], []
    offset = 0
    for series in range(n_series):
        rid, sid = f'replay-{series:04}', f'series-{series:04}'
        segments = 12
        t = np.arange(0., segments * 13., .5)
        n = len(t)
        goal_slots = {}
        for segment in range(segments):
            if rng.random() < .45:
                goal_slots[segment] = int(rng.integers(0, 2))
                stamp = segment * 13. + 8.
                goals.append(dict(replay_id=rid, series_id=sid, season=rl.VAL_SEASON, validated=True,
                                  scoring_team=goal_slots[segment], time=stamp, last_live_time=stamp-.1))
        replays.append(dict(replay_id=rid, series_id=sid, season=rl.VAL_SEASON, validated=True,
                            observed_start_time=float(t[0]), observed_end_time=float(t[-1]),
                            terminal_time=np.nan, terminal_verified=False,
                            gap_start_times='[]', gap_end_times='[]'))
        for team in (0, 1):
            p, b = np.zeros((n, 6, 8)), np.zeros((n, 6))
            touch = np.full(n, -1)
            a = dict(time=t.copy(), players=p, ball=b, touch=touch, live=np.ones(n),
                     segment=np.repeat(np.arange(segments), 26), remaining=np.zeros(n),
                     score_diff=np.zeros(n), overtime=np.zeros(n))
            for segment in range(segments):
                ii = np.flatnonzero(a['segment'] == segment)
                local = t[ii] - segment * 13.
                latency = float(rng.integers(0, 9)) / 2.
                censored = segment % 5 == 0
                p[ii, :, 6] = rng.uniform(10., 90.)
                p[ii, 0, 1] = np.where((local >= latency + .5) & (not censored),
                                      rl.GOAL_Y + 1400., 0.)
                p[ii, 0, 1] = np.where((local >= latency + 1.) & (not censored),
                                      rl.GOAL_Y + 1000., p[ii, 0, 1])
                b[ii, 0] = rng.choice([-2400., 0., 2400.])
                b[ii, 1] = rng.choice([-2000., 2000.])
                a['remaining'][ii] = rng.choice([45., 120., 240.], p=[.65, .2, .15])
                a['score_diff'][ii] = rng.choice([-1., 1.])
                touch[ii[0]], touch[ii[1]] = 0, 3
                a['live'][ii[-1]] = 0
            blocks.append(a)
            metadata.append(dict(meta(team), series_id=sid, replay_id=rid, start=offset, stop=offset+n))
            offset += n
    np.savez_compressed(directory / 'compact-0000.npz',
                        **{key: np.concatenate([b[key] for b in blocks]) for key in rl.REQUIRED})
    pd.DataFrame(metadata).to_parquet(directory / 'compact-0000.parquet', index=False)
    atomic_json(root / 'extraction.json', dict(synthetic_fixture=True,
                note='Paired canonical arrays for software verification, not empirical observations or a physical match simulation'))
    return root, (pd.DataFrame(goals), pd.DataFrame(replays))


class RotationLatencyTests(unittest.TestCase):
    def test_immutable_arrays_and_canonical_views(self):
        a = simple_arrays()
        copies = {k: v.copy() for k, v in a.items()}
        for value in a.values():
            value.flags.writeable = False
        for team in (0, 1):
            rows, audit = extract(a, team)
            self.assertEqual(audit['candidate_losses'], 1)
            np.testing.assert_allclose(rows.latency, 2.)
            self.assertTrue(rows.recovered.all())
        for key in a:
            np.testing.assert_array_equal(a[key], copies[key])

    def test_zero_latency_and_strict_goal_side(self):
        a = simple_arrays()
        a['players'][:, 0, 1] = rl.GOAL_Y + 1000.
        rows, _ = extract(a)
        self.assertTrue(rows.latency.eq(0).all())
        a['ball'][:, 1] = a['players'][:, 0, 1]
        rows, _ = extract(a)
        self.assertFalse(rows.recovered.any())
        self.assertTrue(rows.latency.eq(rl.HORIZON).all())

    def test_thresholds_and_known_demolition(self):
        a = simple_arrays()
        a['players'][:, 0, 1] = rl.GOAL_Y + 1300.
        rows, _ = extract(a)
        self.assertTrue(rows.loc[rows.threshold.eq(1500), 'recovered'].iloc[0])
        self.assertFalse(rows.loc[rows.threshold.eq(1200), 'recovered'].iloc[0])
        a['players'][:, 0, 7] = 1
        self.assertFalse(extract(a)[0].recovered.any())

    def test_stoppage_censors_before_recovery(self):
        a = simple_arrays()
        a['live'][6:] = 0
        rows, _ = extract(a)
        self.assertTrue(rows.latency.eq(2.).all())
        self.assertTrue(rows.censor_reason.eq('stoppage').all())
        self.assertFalse(rows.recovered.any())

    def test_gap_and_hidden_boundary(self):
        for variant in ('time', 'segment'):
            a = simple_arrays()
            a[variant][4:] += 2
            rows, _ = extract(a)
            self.assertTrue(rows.latency.eq(.5).all())
            self.assertFalse(rows.recovered.any())

    def test_touch_memory_resets_and_unknown_states(self):
        for key, value in [('live', 0), ('overtime', 1), ('segment', -1), ('remaining', np.nan)]:
            a = simple_arrays()
            a[key][1] = value
            self.assertTrue(extract(a)[0].empty)
        a = simple_arrays()
        a['score_diff'][2] = np.nan
        rows, audit = extract(a)
        self.assertTrue(rows.empty)
        self.assertEqual(audit['unknown_score_losses'], 1)

    def test_geometry_missingness_and_truncated_followup(self):
        a = simple_arrays()
        a['players'][4, 1, 1] = np.nan
        rows, _ = extract(a)
        self.assertTrue(rows.censor_reason.eq('missing_geometry').all())
        self.assertTrue(rows.latency.eq(.5).all())
        a = {k: v[:4] for k, v in simple_arrays().items()}
        rows, _ = extract(a)
        self.assertTrue(rows.censor_reason.eq('end_of_replay').all())
        self.assertFalse(rows.recovered.any())

    def test_unknown_live_censors_at_last_known_frame(self):
        a = simple_arrays()
        a['live'][4] = np.nan
        rows, _ = extract(a)
        self.assertTrue(rows.latency.eq(.5).all())
        self.assertTrue(rows.censor_reason.eq('gap_or_segment_boundary').all())

    def test_native_outcome_window_terminal_gap_and_brackets(self):
        goals, replay = event_tables()
        self.assertEqual(rl.concession_label(1., 0, goals, replay)[0], 0.)
        replay['observed_end_time'] = 5.
        self.assertTrue(np.isnan(rl.concession_label(1., 0, goals, replay)[0]))
        replay.update(terminal_verified=True, terminal_time=5.)
        self.assertEqual(rl.concession_label(1., 0, goals, replay)[0], 0.)
        replay.update(gap_start_times='[2]', gap_end_times='[3]')
        self.assertTrue(np.isnan(rl.concession_label(1., 0, goals, replay)[0]))
        goals = pd.DataFrame([dict(validated=True, scoring_team=1, time=4., last_live_time=3.9)])
        self.assertEqual(rl.concession_label(1., 0, goals, replay)[0], 1.)
        goals['time'], goals['last_live_time'] = 11.1, 10.9
        self.assertTrue(np.isnan(rl.concession_label(1., 0, goals, replay)[0]))
        replay['validated'] = False
        self.assertTrue(np.isnan(rl.concession_label(1., 0, goals, replay)[0]))

    def test_km_exact_integral_ties_and_zero(self):
        self.assertAlmostEqual(rl.km_rmst([0., 2., 10.], [True, True, False]), 4.)
        self.assertAlmostEqual(rl.km_rmst([2., 2., 10.], [True, False, False]), 22/3)
        self.assertAlmostEqual(rl.km_rmst([0.], [True]), 0.)
        with self.assertRaises(ValueError):
            rl.km_rmst([1., 2.], [True, False])

    def test_weighted_km_matches_explicit_series_duplicates(self):
        durations = np.array([0., 2., 10., 4., 10.])
        events = np.array([1, 1, 0, 1, 0], bool)
        weights = np.array([2, 2, 2, 1, 1])
        self.assertAlmostEqual(rl.km_rmst(durations, events, weights),
                              rl.km_rmst(np.repeat(durations, weights), np.repeat(events, weights)))

    def test_cluster_bootstrap_matches_explicit_draws(self):
        records = []
        for group in range(8):
            for score in (-1, 1):
                records.append(dict(series_id=str(group), latency=float(group%3+3+(group%2 if score == -1 else 0)),
                                    recovered=True, score_diff=score, remaining=45.))
        data = pd.DataFrame(records)
        fit = rl.km_contrast(data)
        rng = np.random.default_rng(rl.SEED)
        contributions = np.arange(8)%2
        values = []
        for _ in range(rl.N_BOOTSTRAP):
            counts = rng.multinomial(8, np.ones(8)/8)
            values.append(counts @ contributions / counts.sum())
        np.testing.assert_allclose([fit['ci_low'], fit['ci_high']], np.quantile(values, [.025, .975]))

    def test_logit_matches_statsmodels_and_rejects_separation(self):
        import statsmodels.api as sm
        rng = np.random.default_rng(rl.SEED)
        x = np.column_stack([np.ones(400), rng.normal(size=(400, 3))])
        y = rng.binomial(1, rl.expit(x @ np.array([-.5, .3, -.2, .1])))
        beta, _ = rl.fit_logit(x, y)
        np.testing.assert_allclose(beta, sm.Logit(y, x).fit(disp=False).params, atol=1e-7)
        with self.assertRaises(ValueError):
            rl.fit_logit(x, (x[:, 1] > 0).astype(float))

    def test_logit_weighted_matches_duplicated_rows(self):
        rng = np.random.default_rng(rl.SEED)
        x = np.column_stack([np.ones(100), rng.normal(size=(100, 2))])
        y = rng.binomial(1, .4, len(x))
        weights = rng.integers(0, 4, len(x))
        a, _ = rl.fit_logit(x, y, weights)
        b, _ = rl.fit_logit(np.repeat(x, weights, axis=0), np.repeat(y, weights))
        np.testing.assert_allclose(a, b, atol=1e-8)

    def test_empty_pilot_and_incomplete_bootstrap_suppress_claims(self):
        empty = rl.analyze(pd.DataFrame())
        self.assertEqual(len(empty['contrasts']), len(rl.THRESHOLDS))
        self.assertFalse(any(empty['decisions'].values()))
        pilot = rl.analyze(extract()[0], pilot=True)
        for models in pilot['contrasts'].values():
            self.assertTrue(all(m['estimate'] is None and m['status'] == 'feasibility_only' for m in models.values()))
        incomplete = rl.bootstrap_result(1., [1., np.nan], pd.DataFrame())
        self.assertIsNone(incomplete['ci_low'])
        self.assertEqual(incomplete['status'], 'bootstrap_incomplete')

    def test_threshold_direction_gate(self):
        fit = dict(status='fit', estimate=1., ci_low=.1, ci_high=2.)
        contrasts = {str(r): {name: dict(fit) for name in rl.MODELS} for r in rl.THRESHOLDS}
        self.assertTrue(rl.direction_gate(contrasts, rl.MODELS[0]))
        contrasts['1200'][rl.MODELS[0]]['estimate'] = -1.
        self.assertFalse(rl.direction_gate(contrasts, rl.MODELS[0]))

    def test_metadata_and_path_guards_before_array_load(self):
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=OUTPUT_ROOT) as tmp:
            root, _ = write_fixture(Path(tmp)/'compact', 2)
            path = root / rl.VAL_SEASON / 'compact-0000.parquet'
            data = pd.read_parquet(path)
            data.loc[0, 'season'] = 'rlcs-2026'
            data.to_parquet(path, index=False)
            with patch.object(rl.np, 'load', side_effect=AssertionError('numeric arrays opened')):
                with self.assertRaises(ValueError):
                    rl.inventory(root)
            forbidden = Path(tmp)/'rlcs-2026'
            forbidden.mkdir()
            link = Path(tmp)/'alias'
            link.symlink_to(forbidden, target_is_directory=True)
            with self.assertRaises(ValueError):
                rl.guard_path(link)
            with self.assertRaises(ValueError):
                rl.analyze(pd.DataFrame([dict(season='rlcs-2026', split='val')]))

    def test_inventory_duplicate_and_missing_perspective(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT_ROOT) as tmp:
            root, _ = write_fixture(Path(tmp)/'compact', 2)
            path = root/rl.VAL_SEASON/'compact-0000.parquet'
            data = pd.read_parquet(path)
            data.iloc[:-1].to_parquet(path, index=False)
            with self.assertRaises(ValueError):
                rl.inventory(root)
            pd.concat([data, data.iloc[:1]]).to_parquet(path, index=False)
            with self.assertRaises(ValueError):
                rl.inventory(root)

    def test_pilot_is_seeded_whole_series_and_exact_count(self):
        rows = [dict(series_id=f's-{i:03}', replay_id=f'r-{i}-{j}', focal_team=team)
                for i in range(rl.PILOT_SERIES+7) for j in range(2) for team in (0, 1)]
        frame = pd.DataFrame(rows)
        shards = [(None, None, frame)]
        chosen = rl.select_series(shards, True)
        self.assertEqual(len(chosen), rl.PILOT_SERIES)
        self.assertEqual(chosen, rl.select_series([(None, None, frame.iloc[::-1])], True))
        self.assertTrue(frame.loc[frame.series_id.isin(chosen)].groupby('series_id').size().eq(4).all())
        with self.assertRaises(ValueError):
            rl.select_series([(None, None, frame.loc[frame.series_id.eq(chosen[0])])], True)

    def test_pilot_end_to_end_never_calls_inference(self):
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=OUTPUT_ROOT) as tmp:
            root = Path(tmp)
            compact, events = write_fixture(root/'compact', rl.PILOT_SERIES)
            with patch.object(rl, 'km_contrast', side_effect=AssertionError('pilot inferred')):
                with patch.object(rl, 'ols_contrast', side_effect=AssertionError('pilot inferred')):
                    with patch.object(rl, 'logit_contrast', side_effect=AssertionError('pilot inferred')):
                        result = rl.run(compact, root/'pilot.json', root/'audit', pilot=True,
                                        synthetic_events=events)
            self.assertEqual(result['provenance']['series'], rl.PILOT_SERIES)
            self.assertEqual(result['reporting_scope'], 'feasibility_only')
            self.assertFalse(result['finding_eligible'])
            self.assertTrue(all(m['estimate'] is None for row in result['contrasts'].values() for m in row.values()))


if __name__ == '__main__':
    unittest.main()
