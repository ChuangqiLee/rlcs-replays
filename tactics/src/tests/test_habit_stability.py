"""Local synthetic tests; no empirical compact or network access required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

MODULE = Path(__file__).resolve().parents[1]/'tactics_code/habit_stability.py'
TEMP_ROOT = MODULE.parents[2]/'logs'
TEMP_ROOT.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('habit_stability', MODULE)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def fixture(samples=200, season=None, replay='game', team=0):
    season = season or h.ALLOWED_SEASONS[0]
    ids = [f'platform:{i}' for i in range(6)]
    ids = ids if team == 0 else ids[3:]+ids[:3]
    meta = dict(replay_id=replay, series_id='series-'+season, season=season,
                split='val' if season == h.VAL_SEASON else 'train',
                player_ids=json.dumps(ids), roster_id=h.roster_key(ids[:3]), focal_team=team,
                opponent_roster_id=h.roster_key(ids[3:]), fps=10., start=0, stop=samples,
                state_decoding='per_replay_decoded', state_decoding_details=json.dumps({'failures': []}))
    players = np.zeros((samples, 6, 8))
    players[:, :, 1] = [-1000, -1000, 1000, 0, 0, 0]
    players[:, :, 2] = 100
    players[:, :, 4] = -2200
    players[:, :, 6] = 127.5
    ball = np.zeros((samples, 6))
    ball[:, 1] = -2000
    ball[:, 2] = 100
    arrays = dict(players=players, ball=ball, time=np.arange(samples)/meta['fps'],
                  live=np.ones(samples, bool), segment=np.zeros(samples, int),
                  frame=np.arange(samples), score_diff=np.zeros(samples),
                  remaining=np.full(samples, 100.), overtime=np.zeros(samples))
    return meta, arrays


def synthetic_cells(seed=102):
    """Legitimate three-member rosters, remixed between adjacent seasons."""
    rng = np.random.default_rng(seed)
    players = [f'p{i}' for i in range(90)]
    traits = dict(zip(players, rng.normal(0, 2, len(players))))
    rows, history, roster_values = [], {}, {}
    # Half of the teams persist; the other half acquire different teammates.
    for season_index, season in enumerate(h.ALLOWED_SEASONS):
        tail = players[45:] if season_index == 0 else list(np.roll(players[45:], season_index))
        order = players[:45]+tail
        for start in range(0, len(order), 3):
            members = order[start:start+3]
            roster = h.roster_key(members)
            roster_values.setdefault(roster, rng.normal())
            for player in members:
                history[(player, season)] = {roster: frozenset(members)-{player}}
                row = dict(identity_id=player, season=season, roster_id=roster)
                value = traits[player]+roster_values[roster]+rng.normal(0, .7)+season_index*.15
                for j, habit in enumerate(h.HABITS):
                    row[habit] = value*(j+1)
                    row[habit+'_n'] = h.MIN_REPLAYS
                rows.append(row)
    return pd.DataFrame(rows), history


class HabitTests(unittest.TestCase):
    def test_readonly_features_exact_definitions(self):
        meta, arrays = fixture()
        original = {k: v.copy() for k, v in arrays.items()}
        for a in arrays.values():
            a.flags.writeable = False
        rows = h.game_habits(meta, arrays)
        a, b, c = rows
        self.assertEqual(a['last_man_share'], .5)
        self.assertEqual(b['last_man_share'], .5)
        self.assertEqual(c['last_man_share'], 0)
        self.assertEqual(a['own_goal_depth'], 5120-1000)
        self.assertEqual(a['own_third_depth'], a['own_goal_depth'])
        self.assertEqual(a['boost_mean'], .5)
        self.assertEqual(a['supersonic_share'], 1.)
        self.assertEqual(a['ball_proximity_share'], 1.)
        self.assertEqual(c['ball_proximity_share'], 0.)
        self.assertEqual(a['aerial_share'], 0.)
        self.assertEqual(a['rotation_back_speed'], 2200.)
        for key in arrays:
            np.testing.assert_array_equal(arrays[key], original[key])

    def test_missing_exposure_demolition_and_ball(self):
        meta, arrays = fixture()
        arrays['players'][:101, 0, 7] = 1
        arrays['players'][:, 1, 7] = np.nan
        arrays['ball'][:, :3] = np.nan
        rows = h.game_habits(meta, arrays)
        self.assertTrue(np.isnan(rows[0]['boost_mean']))
        self.assertTrue(np.isnan(rows[1]['own_third_depth']))
        self.assertTrue(np.isnan(rows[1]['last_man_share']))
        self.assertEqual(rows[1]['unknown_demolition_samples'], len(arrays['time']))
        self.assertEqual(rows[1]['boost_mean'], .5)

    def test_exact_thresholds_and_exposure(self):
        meta, arrays = fixture(samples=100)
        arrays['players'][:, 0, 2] = 300
        self.assertEqual(h.game_habits(meta, arrays)[0]['aerial_share'], 0)
        arrays['players'][:, 0, 2] += 1
        self.assertEqual(h.game_habits(meta, arrays)[0]['aerial_share'], 1)
        arrays['ball'][:, 1] = -1706.67
        self.assertTrue(np.isnan(h.game_habits(meta, arrays)[0]['own_third_depth']))
        arrays['live'][0] = False
        self.assertTrue(np.isnan(h.game_habits(meta, arrays)[0]['boost_mean']))

    def test_slot_equivariance(self):
        meta, arrays = fixture()
        baseline = h.game_habits(meta, arrays)
        order = [2, 0, 1, 3, 4, 5]
        ids = json.loads(meta['player_ids'])
        meta['player_ids'] = json.dumps([ids[i] for i in order])
        arrays['players'] = arrays['players'][:, order]
        by_id = {r['identity_id']: r for r in h.game_habits(meta, arrays)}
        for row in baseline:
            for habit in h.HABITS:
                self.assertEqual(row[habit], by_id[row['identity_id']][habit])

    def test_invalid_id_and_roster(self):
        meta, arrays = fixture()
        meta['roster_id'] = 'organization-name'
        with self.assertRaises(ValueError):
            h.game_habits(meta, arrays)
        meta, arrays = fixture()
        meta['player_ids'] = json.dumps(['same']*6)
        with self.assertRaises(ValueError):
            h.game_habits(meta, arrays)

    def test_season_split_and_path_guards(self):
        for season, split in [('rlcs-2026', 'test'), (h.VAL_SEASON, 'train'), ('unknown', 'train')]:
            meta, arrays = fixture()
            meta.update(season=season, split=split)
            with self.assertRaises(ValueError):
                h.game_habits(meta, arrays)
        with self.assertRaises(ValueError):
            h.guard_path('/tmp/rlcs-2026/compact')
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as root:
            root = Path(root)
            (root/'test').mkdir()
            (root/'innocent').symlink_to(root/'test')
            with self.assertRaises(ValueError):
                h.guard_path(root/'innocent')

    def test_inconsistent_perspectives(self):
        first, _ = fixture(team=0)
        second, _ = fixture(team=1)
        h.validate_pairs([[first, second]])
        second['player_ids'] = first['player_ids']
        second['roster_id'] = first['roster_id']
        with self.assertRaises(ValueError):
            h.validate_pairs([[first, second]])

    def test_equal_replay_aggregation_not_equal_roster(self):
        rows = []
        for i in range(10):
            meta, arrays = fixture(replay=str(i))
            row = h.game_habits(meta, arrays)[0]
            row['roster_id'] = 'a' if i == 0 else 'b'
            row['own_goal_depth'] = 0 if i == 0 else 10
            rows.append(row)
        games = pd.DataFrame(rows)
        cells = h.aggregate_games(games)
        means = h.season_means(cells, 'own_goal_depth')
        self.assertEqual(means.own_goal_depth.iloc[0], 9)
        self.assertEqual(means.own_goal_depth_n.iloc[0], 10)
        with self.assertRaises(ValueError):
            h.aggregate_games(pd.concat([games, games.iloc[:1]]))

    def test_icc_known_variance_recovered(self):
        rng = np.random.default_rng(1982)
        target_variance, error_variance = 4., 1.
        a = (rng.normal(0, np.sqrt(target_variance), (50000, 1))
             + rng.normal(0, np.sqrt(error_variance), (50000, 2)))
        expected = target_variance/(target_variance+error_variance)
        self.assertAlmostEqual(float(h.icc21(a)), expected, delta=.015)

    def test_icc_agreement_penalizes_season_shift(self):
        x = np.arange(40.)
        exact = np.column_stack([x, x])
        shifted = np.column_stack([x, x+100])
        self.assertEqual(float(h.icc21(exact)), 1.)
        self.assertLess(float(h.icc21(shifted)), .1)
        self.assertEqual(float(h.rho_many(x, x+100)), 1.)
        self.assertLess(float(h.icc21(np.column_stack([x, -x]))), 0)

    def test_ranks_ties_and_constant(self):
        x, y = np.array([0, 1, 1, 4.]), np.array([3, 2, 2, 1.])
        self.assertAlmostEqual(float(h.rho_many(x, y)), spearmanr(x, y).statistic)
        self.assertTrue(np.isnan(h.rho_many(x, np.ones_like(y))))

    def test_minima_habit_specific_and_no_bridging(self):
        cells, history = synthetic_cells()
        before, after = h.ALLOWED_SEASONS[:2]
        mask = (cells.identity_id == 'p0') & (cells.season == after)
        cells.loc[mask, 'boost_mean_n'] = h.MIN_REPLAYS-1
        pair = h.pair_means(cells, 'boost_mean', before, after, history)
        self.assertNotIn('p0', set(pair.identity_id))
        self.assertIn('p0', set(h.pair_means(cells, 'aerial_share', before, after, history).identity_id))
        with self.assertRaises(ValueError):
            h.pair_means(cells, 'aerial_share', before, h.ALLOWED_SEASONS[-1], history)
        report, _, _ = h.stability(pair.iloc[:h.MIN_PLAYERS-1], 10, 10, np.random.default_rng(1))
        self.assertEqual(report['status'], 'insufficient_data')

    def test_history_includes_unusable_replays(self):
        cells, history = synthetic_cells()
        before, after = h.ALLOWED_SEASONS[:2]
        history[('p0', before)]['extra'] = frozenset(['other', 'players'])
        pair = h.pair_means(cells, 'boost_mean', before, after, history)
        self.assertEqual(pair.set_index('identity_id').loc['p0', 'roster_group'], 'mixed')
        self.assertEqual(pair.set_index('identity_id').loc['p1', 'roster_group'], 'same')
        self.assertEqual(pair.set_index('identity_id').loc['p45', 'roster_group'], 'changed')

    def test_player_bootstrap_keeps_paired_seasons(self):
        x = np.arange(30.)
        r, i = h.bootstrap_stats(x, x, 100, np.random.default_rng(42))
        np.testing.assert_allclose(r, 1.)
        np.testing.assert_allclose(i, 1.)
        report = h.interval(np.r_[np.ones(94), np.full(6, np.nan)], 100)
        self.assertIsNone(report['ci95'])

    def test_retention_ratio_and_weak_denominator(self):
        n = h.MIN_PLAYERS+10
        pair = pd.DataFrame(dict(identity_id=[f'p{i}' for i in range(n*2)],
                                 x=np.tile(np.arange(n), 2), y=np.tile(np.arange(n), 2),
                                 roster_group=['same']*n+['changed']*n))
        result = h.retention(pair, 200, np.random.default_rng(42))
        self.assertEqual(result['ratio'], 1.)
        self.assertEqual(result['ratio_uncertainty']['ci95'], [1., 1.])
        pair.loc[pair.roster_group == 'same', 'y'] = -np.arange(n)
        result = h.retention(pair, 200, np.random.default_rng(42))
        self.assertEqual(result['ratio_status'], 'weak_denominator')
        self.assertEqual(result['ratio'], -1.)
        self.assertIsNone(result['ratio_uncertainty']['ci95'])

    def test_bh_fixed_family_including_missing(self):
        p = [.01, .02]+[None]*(len(h.HABITS)-2)
        q = h.bh_fixed(p)
        self.assertEqual(q[:2], [.08, .08])
        self.assertEqual(q[2:], [None]*(len(h.HABITS)-2))

    def test_crossed_model_and_component_shares(self):
        cells, _ = synthetic_cells()
        result = h.variance_decomposition(cells, 'boost_mean')
        self.assertEqual(result['status'], 'fit', result)
        self.assertEqual(result['covariance_design_rank'], 3)
        components = result['primary']['variance']
        self.assertEqual(set(components), {'player', 'roster', 'residual'})
        self.assertGreater(components['player'], components['residual'])
        self.assertGreater(components['roster'], components['residual'])
        self.assertAlmostEqual(sum(result['primary']['shares'].values()), 1.)

    def test_fallback_is_labeled_and_primary_unavailable(self):
        cells, _ = synthetic_cells()
        cells['roster_id'] = cells.identity_id.map(lambda p: 'fixed-'+str(int(p[1:])//3))
        result = h.variance_decomposition(cells, 'boost_mean')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['fallback']['label'], 'descriptive_player_only_roster_unseparated')
        self.assertIsNone(result['fallback']['roster_variance'])

    def test_design_rank_catches_alias(self):
        frame = pd.DataFrame(dict(identity_id=['a', 'a', 'b', 'b'], roster_id=['a', 'a', 'b', 'b']))
        self.assertEqual(h.covariance_design_rank(frame), 2)

    def test_crossed_optimizer_failure_triggers_labeled_fallback(self):
        cells, _ = synthetic_cells()
        with patch.object(h, 'fit_variances', side_effect=[{'status': 'failed', 'attempts': []},
                                                         {'status': 'fit', 'attempts': []}]):
            result = h.variance_decomposition(cells, 'boost_mean')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['reason'], 'crossed_fit_failed')
        self.assertEqual(result['fallback']['label'], 'descriptive_player_only_roster_unseparated')

    def test_invalid_offsets_rejected_before_payload(self):
        meta, arrays = fixture()
        meta['_shard'] = 'synthetic'
        schema = {'synthetic': {k: dict(shape=list(a.shape), dtype=str(a.dtype), fortran=False)
                                for k, a in arrays.items()}}
        h.validate_offsets([[meta]], schema)
        for start, stop in [(-1, 100), (0, 201), (.5, 100), (20, 10)]:
            with self.subTest(start=start, stop=stop):
                bad = dict(meta, start=start, stop=stop)
                with self.assertRaises(ValueError):
                    h.validate_offsets([[bad]], schema)

    def test_permutation_and_bootstrap_reproducible(self):
        cells, history = synthetic_cells()
        pair = h.pair_means(cells, 'boost_mean', *h.ALLOWED_SEASONS[:2], history)
        a, _, _ = h.stability(pair, 100, 100, np.random.default_rng(42))
        b, _, _ = h.stability(pair, 100, 100, np.random.default_rng(42))
        self.assertEqual(a, b)
        self.assertGreaterEqual(a['p_value'], 1/(100+1))
        self.assertLess(a['p_value'], .05)

    def test_heldout_aggregates_cannot_enter_inference(self):
        cells, history = synthetic_cells()
        cells.loc[cells.index[0], 'season'] = 'rlcs-2026'
        with self.assertRaises(ValueError):
            h.analyze(cells, history)

    def test_end_to_end_synthetic_compact_avoids_test_and_writes_outputs(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root = Path(tmp)
            compact = root/'compact'
            compact.mkdir()
            (compact/'extraction.json').write_text(json.dumps({'state_map': {'state_decoding': 'per_replay_decoded'}}))
            for season in h.ALLOWED_SEASONS:
                folder = compact/season
                folder.mkdir()
                metas, payloads = [], []
                for team in (0, 1):
                    meta, arrays = fixture(season=season, replay=season, team=team)
                    meta.update(start=team*200, stop=(team+1)*200)
                    metas.append(meta)
                    payloads.append(arrays)
                pd.DataFrame(metas).to_parquet(folder/'compact-0000.parquet', index=False)
                np.savez_compressed(folder/'compact-0000.npz', **{
                    k: np.concatenate([a[k] for a in payloads]) for k in h.REQUIRED})
            forbidden = compact/'rlcs-2026'
            forbidden.mkdir()
            (forbidden/'compact-0000.parquet').write_text('unreadable held-out sentinel')
            prereg = MODULE.parents[2]/'docs/RQ4_habits_prereg.md'
            for mode in ('full', 'smoke'):
                destination = root/mode
                argv = ['--compact', str(compact), '--output-dir', str(destination), '--prereg', str(prereg)]
                if mode == 'smoke':
                    argv += ['--max-replays', str(len(h.ALLOWED_SEASONS))]
                h.main(argv)
                result = json.loads((destination/'rq4_habits.json').read_text())
                self.assertFalse(result['test_opened'])
                self.assertEqual(result['processed_replays'], len(h.ALLOWED_SEASONS))
                self.assertEqual(len(pd.read_parquet(destination/'player_replays.parquet')), len(h.ALLOWED_SEASONS)*6)
                if mode == 'full':
                    for transition in result['transitions']:
                        self.assertTrue(all(r['overall']['status'] == 'insufficient_data' for r in transition['habits']))
                else:
                    self.assertEqual(result['status'], 'smoke_no_inference')
            pd.testing.assert_frame_equal(pd.read_parquet(root/'full/player_replays.parquet').sort_values(['identity_id', 'season']).reset_index(drop=True),
                                          pd.read_parquet(root/'smoke/player_replays.parquet').sort_values(['identity_id', 'season']).reset_index(drop=True))


if __name__ == '__main__':
    unittest.main(verbosity=2)
