"""Local synthetic tests; no empirical observations and no network access."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from statsmodels.regression.mixed_linear_model import MixedLM, MixedLMParams

from tactics_code import pushup_heterogeneity as h


def synthetic_panel(seed=h.SEED, groups=12, series=10, frames_per_cell=24):
    rng = np.random.default_rng(seed)
    rows, games, raw = [], [], []
    intercepts = rng.normal(0, 250, groups)
    slopes = rng.normal(0, 450, groups)
    for season in h.ALLOWED_SEASONS:
        split = 'val' if season == h.VAL_SEASON else 'train'
        for s in range(series):
            for g in range(groups):
                for late in (0, 1):
                    for trailing in (0, 1):
                        y = (3500 + intercepts[g] + 120*late - 90*trailing +
                             (400 + slopes[g])*late*trailing + rng.normal(0, 180, frames_per_cell))
                        identity = dict(season=season, split=split, series_id=f'{season}/series{s}',
                                        roster_id=f'team{g}', player_id=f'player{g}')
                        row = dict(identity, late=late, trailing=trailing, n=len(y), sy=y.sum(), sy2=y@y,
                                   seconds=len(y)/10)
                        rows.append(row)
                        if season == h.VAL_SEASON:
                            raw.extend(dict(identity, late=late, trailing=trailing, y=v) for v in y)
                games.append(dict(identity, replay_id=f'{season}/{s}/{g}',
                                  win=int(rng.random() < (g+1)/(groups+1))))
    return pd.DataFrame(rows), pd.DataFrame(games), pd.DataFrame(raw)


def compact_fixture(root):
    """All development seasons, both perspectives, canonical IDs and certificates."""
    root.mkdir(parents=True, exist_ok=True)
    (root/'extraction.json').write_text(json.dumps({'state_map': {'state_decoding': 'per_replay_decoded'}}))
    events = []
    for season in h.ALLOWED_SEASONS:
        directory = root/season
        directory.mkdir(exist_ok=True)
        chunks, metadata, offset = [], [], 0
        for game in range(3):
            for focal in (0, 1):
                n, fps = 120, 10.
                t = np.arange(n)/fps
                rem = np.repeat([180., 120., 60., 30.], n//4)
                score = np.tile(np.repeat([-1, 1], n//8), 4)*(1 if focal == 0 else -1)
                players = np.zeros((n, 6, 8))
                players[:, :, 1] = np.arange(6)*500 - 2500
                players[:, :, 0] = np.sin(t)[:, None]*100
                ball = np.zeros((n, 6))
                a = dict(time=t, frame=np.arange(n), players=players, ball=ball,
                         live=np.ones(n, bool), segment=np.zeros(n, int), score_diff=score,
                         remaining=rem, overtime=np.zeros(n, int))
                ids = [f'platform:{i}' for i in range(6)]
                if focal:
                    ids = ids[3:] + ids[:3]
                meta = dict(replay_id=f'{season}/game{game}', season=season,
                            split='val' if season == h.VAL_SEASON else 'train',
                            series_id=f'{season}/series{game}', focal_team=focal,
                            player_ids=json.dumps(ids), roster_id=h.roster_key(ids[:3]),
                            opponent_roster_id=h.roster_key(ids[3:]), fps=fps,
                            state_decoding='per_replay_decoded', state_decoding_details=json.dumps({'failures': []}),
                            start=offset, stop=offset+n, region='EU', group_path='[]')
                metadata.append(meta)
                chunks.append(a)
                offset += n
            events.append(dict(replay_id=f'{season}/game{game}', season=season,
                               series_id=f'{season}/series{game}', validated=True, terminal_verified=True,
                               header_goals_0=2, header_goals_1=1))
        np.savez_compressed(directory/'compact-0000.npz', **{k: np.concatenate([a[k] for a in chunks]) for k in chunks[0]})
        pd.DataFrame(metadata).to_parquet(directory/'compact-0000.parquet', index=False)
    return pd.DataFrame(events)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.games, cls.raw = synthetic_panel()

    def test_exact_likelihood_score_hessian_and_blups(self):
        frame = h.cohort(self.frame, h.VAL_SEASON)
        r = self.raw
        x = np.column_stack([np.ones(len(r)), r.late, r.trailing, r.late*r.trailing])
        full = MixedLM(r.y.to_numpy(), x, groups=r.roster_id, exog_re=x[:, [0, 3]])
        compact = h.compressed_model(frame, 'roster_id')
        parameters = MixedLMParams.from_components(fe_params=np.array([3400., 100., -80., 450.]),
                                                   cov_re=np.array([[2., .3], [.3, 4.]]))
        for reml in (False, True):
            for model in (full, compact):
                model.reml, model.cov_pen, model.fe_pen, model._freepat, model._cov_sing = reml, None, None, None, 0
            self.assertAlmostEqual(full.loglike(parameters), compact.loglike(parameters), places=6)
            np.testing.assert_allclose(full.score_full(parameters, True)[1],
                                       compact.score_full(parameters, True)[1], rtol=1e-8, atol=1e-6)
            np.testing.assert_allclose(full.hessian(parameters)[0], compact.hessian(parameters)[0], rtol=1e-7, atol=1e-6)
        a = full.fit(reml=False, method='bfgs', gtol=1e-5/len(full.endog), maxiter=h.MAXITER, disp=False)
        b = compact.fit(reml=False, method='bfgs', gtol=1e-5/len(compact.endog), maxiter=h.MAXITER, disp=False)
        self.assertTrue(a.converged and b.converged)
        np.testing.assert_allclose(a.fe_params, b.fe_params, rtol=1e-6, atol=1e-4)
        np.testing.assert_allclose(a.cov_re, b.cov_re, rtol=1e-5)
        self.assertAlmostEqual(a.scale, b.scale, places=3)
        for identity in a.random_effects:
            np.testing.assert_allclose(a.random_effects[identity], b.random_effects[identity], rtol=1e-5, atol=1e-3)

    def test_fit_recovers_interaction_and_identity_ranking(self):
        fit = h.fit_model(h.cohort(self.frame, h.VAL_SEASON), 'roster_id')
        self.assertEqual(fit['status'], 'fit')
        self.assertTrue(np.isfinite(fit['fixed']['late:trailing']))
        self.assertEqual(fit['cr1_fixed']['n_series'], self.games[self.games.split == 'val'].series_id.nunique())
        self.assertEqual(len(fit['slopes']), self.raw.roster_id.nunique())
        self.assertAlmostEqual(sum(fit['slopes'].values()), 0., places=4)
        means = self.raw.groupby(['roster_id', 'late', 'trailing']).y.mean().unstack(['late', 'trailing'])
        contrast = means[(1, 1)] - means[(1, 0)] - means[(0, 1)] + means[(0, 0)]
        self.assertGreater(h.rho([fit['slopes'][i] for i in contrast.index], contrast), .95)

    def test_parallel_bootstrap_reproducible(self):
        frame, games, _ = synthetic_panel(groups=5, series=4, frames_per_cell=8)
        frame['seconds'] = h.MIN_MINUTES*60
        serial = h.inference(frame, games, bootstrap=2, workers=1)
        parallel = h.inference(frame, games, bootstrap=2, workers=2)
        self.assertEqual(serial['comparisons'], parallel['comparisons'])

    def test_cr1_matches_explicit_marginal_gls(self):
        f, r = h.cohort(self.frame, h.VAL_SEASON), self.raw
        model = h.compressed_model(f, 'roster_id')
        fit = model.fit(reml=False, method='lbfgs', disp=False)
        # Smaller literal matrices retain the same identity/series crossing.
        r = r.groupby(['roster_id', 'series_id', 'late', 'trailing']).head(2)
        moments = r.assign(n=1, sy=r.y, sy2=r.y**2, seconds=.1).groupby(h.KEYS)[h.SUMS].sum().reset_index()
        actual = np.asarray(h.cr1_fixed(moments, 'roster_id', fit)['covariance'])
        bread, scores = np.zeros((4, 4)), {}
        for _, part in r.groupby('roster_id'):
            x = np.column_stack([np.ones(len(part)), part.late, part.trailing, part.late*part.trailing])
            z = x[:, [0, 3]]
            inv = np.linalg.inv(fit.scale*np.eye(len(part)) + z@fit.cov_re@z.T)
            bread += x.T@inv@x
            row_scores = x*(inv@(part.y.to_numpy()-x@fit.fe_params))[:, None]
            for sid, score in zip(part.series_id, row_scores):
                scores[sid] = scores.get(sid, np.zeros(4)) + score
        meat = np.stack(list(scores.values()))
        g, n, p = len(scores), len(r), x.shape[1]
        expected = np.linalg.inv(bread)@meat.T@meat@np.linalg.inv(bread)*(g/(g-1))*((n-1)/(n-p))
        np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-7)

    def test_eligibility_is_minutes_in_both_and_held_fixed(self):
        f = self.frame.copy()
        fits = {f'{name}/{group}': {'status': 'fit', 'slopes': {f'{prefix}{g}': float(g) for g in range(12)}}
                for name in h.COHORTS for group, prefix in zip(h.GROUPS, ['team', 'player'])}
        initial = h.compare(f, self.games, fits)
        key = f'stability/train/{h.VAL_SEASON}/roster_id'
        self.assertEqual(initial[key]['n_units'], 0)
        f['seconds'] = h.MIN_MINUTES*60
        result = h.compare(f, self.games, fits)
        self.assertEqual(result[key]['rho'], 1.)
        f.loc[(f.roster_id == 'team0') & (f.split == 'val'), 'seconds'] = 0.01
        self.assertNotIn('team0', h.compare(f, self.games, fits)[key]['eligible_ids'])
        fixed = {k: v['eligible_ids'] for k, v in result.items()}
        self.assertIn('team0', h.compare(f, self.games, fits, fixed)[key]['eligible_ids'])
        del fits[f'{h.VAL_SEASON}/roster_id']['slopes']['team0']
        self.assertIsNone(h.compare(f, self.games, fits, fixed)[key]['rho'])
        self.assertTrue(all(v['reported_regardless'] for k, v in result.items() if k.startswith('comeback/')))

    def test_whole_series_resampling_shared_with_games(self):
        f, g = h.series_draw(self.frame, self.games, np.random.default_rng(h.SEED))
        original = self.frame.groupby('series_id').n.sum()
        multiplicity = f.groupby('series_id').n.sum()/original
        gc = g.groupby('series_id').size()/self.games.groupby('series_id').size()
        np.testing.assert_allclose(multiplicity.fillna(0).sort_index(), gc.fillna(0).sort_index())
        self.assertTrue((multiplicity.fillna(0) > 1).any())
        for season in h.ALLOWED_SEASONS:
            self.assertEqual(int(multiplicity.fillna(0).loc[lambda x: x.index.str.startswith(season)].sum()),
                             self.frame[self.frame.season == season].series_id.nunique())

    def test_nonconvergence_fallback_and_failure(self):
        frame = h.cohort(self.frame, h.VAL_SEASON)
        original = MixedLM.fit
        calls = []
        def fail_correlated(model, **kwargs):
            calls.append(kwargs['free'])
            if kwargs['free'] is None:
                raise np.linalg.LinAlgError('synthetic failure')
            return original(model, **kwargs)
        with patch.object(MixedLM, 'fit', fail_correlated):
            fit = h.fit_model(frame, 'roster_id')
        self.assertEqual(fit['status'], 'fallback_diagonal')
        self.assertTrue(any(x is not None for x in calls))
        with patch.object(MixedLM, 'fit', side_effect=np.linalg.LinAlgError('synthetic failure')):
            failed = h.fit_model(frame, 'roster_id')
        self.assertEqual(failed['status'], 'not_estimable')
        self.assertEqual(failed['slopes'], {})

    def test_rho_degenerate(self):
        self.assertIsNone(h.rho([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(h.rho([1, 2], [2, 1]))
        self.assertIsNone(h.rho([1, 2, np.nan], [1, 2, 3]))

    def test_forbidden_seasons_and_symlinks(self):
        with tempfile.TemporaryDirectory(dir=TEST_ARTIFACTS) as tmp:
            root = Path(tmp)
            forbidden = root/'rlcs-2026'
            forbidden.mkdir()
            link = root/'allowed'
            link.symlink_to(forbidden, target_is_directory=True)
            for path in (forbidden, link, root/'test/file'):
                with self.assertRaises(ValueError):
                    h.guard_path(path)
            f = self.frame.copy()
            f.loc[0, 'season'] = 'rlcs-2026'
            with self.assertRaises(ValueError):
                h.inference(f, self.games, bootstrap=0)
            event = pd.DataFrame([dict(season='rlcs-2026', series_id='x', replay_id='x', validated=True,
                                       terminal_verified=True, header_goals_0=1, header_goals_1=0)])
            with self.assertRaises(ValueError):
                h.validate_events(event)

    def test_compact_loaders_parity_and_identity(self):
        with tempfile.TemporaryDirectory(dir=TEST_ARTIFACTS) as tmp:
            root = Path(tmp)
            events = compact_fixture(root/'compact')
            pairs, _ = h.inventory(root/'compact')
            a, games_a, audit_a = h.build_tables(pairs, events, root, smoke=False)
            b, games_b, audit_b = h.build_tables(pairs, events, root, smoke=True)
            pd.testing.assert_frame_equal(a, b)
            pd.testing.assert_frame_equal(games_a, games_b)
            self.assertEqual(audit_a, audit_b)
            meta = pairs[0][0]
            bad = dict(meta, roster_id='display-name')
            with self.assertRaises(ValueError):
                h.identities(bad)
            metadata_path = Path(meta['_shard']).with_suffix('.parquet')
            frame = pd.read_parquet(metadata_path)
            frame.loc[0, 'season'] = 'rlcs-2026'
            frame.to_parquet(metadata_path, index=False)
            with patch.object(h, 'metadata_inventory', side_effect=AssertionError('must not inspect ZIP')):
                with self.assertRaises(ValueError):
                    h.inventory(root/'compact')

    def test_snapshot_geometry_final_score_and_missingness(self):
        with tempfile.TemporaryDirectory(dir=TEST_ARTIFACTS) as tmp:
            root = Path(tmp)
            events = compact_fixture(root/'compact')
            pairs, _ = h.inventory(root/'compact')
            meta = pairs[0][0]
            a = h.read_slice(meta)
            a = {k: v.copy() for k, v in a.items()}
            a['score_diff'][:] = -1
            event = events.set_index('replay_id').loc[meta['replay_id']].to_dict()
            f, games, _ = h.summarize_replay(meta, a, event)
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0]['win'], 1)
            self.assertEqual(games[0]['player_id'], h.identities(meta)[0])
            self.assertAlmostEqual(f.seconds.sum(), len(a['time'])/meta['fps'])
            event['terminal_verified'] = False
            self.assertEqual(h.summarize_replay(meta, a, event)[1], [])
            event['terminal_verified'] = True
            # Missing geometry invalidates player attribution, not team outcome.
            snap = a['remaining'] == h.LATE_SECONDS
            a['players'][snap, 0, 0] = np.nan
            self.assertIsNone(h.summarize_replay(meta, a, event)[1][0]['player_id'])
            # A deficit change within the clock tick must not be guessed.
            a['score_diff'][np.flatnonzero(snap)[-1]] = 0
            self.assertEqual(h.summarize_replay(meta, a, event)[1], [])
            a['remaining'][snap] = h.LATE_SECONDS - 1
            self.assertEqual(h.summarize_replay(meta, a, event)[1], [])

    def test_bootstrap_failure_cannot_trigger_finding(self):
        f = self.frame.copy()
        f['seconds'] = h.MIN_MINUTES*60
        good = {f'{name}/{group}': {'status': 'fit', 'slopes': {f'{prefix}{g}': float(g) for g in range(12)},
                                   'fixed': dict.fromkeys(h.TERMS, 1.)}
                for name in h.COHORTS for group, prefix in zip(h.GROUPS, ['team', 'player'])}
        bad = {k: dict(v, status='fallback_diagonal') for k, v in good.items()}
        with patch.object(h, 'fit_all', side_effect=[good, good, bad]):
            result = h.inference(f, self.games, bootstrap=2)
        for key, value in result['comparisons'].items():
            self.assertFalse(value['finding'])
            if key.startswith('stability/'):
                self.assertEqual(value['bootstrap_successful'], 1)

    def test_invalid_moments_rejected(self):
        for column, value in [('n', 0), ('sy2', -1), ('late', -1), ('player_id', None)]:
            f = self.frame.copy()
            f.loc[0, column] = value
            with self.assertRaises(ValueError):
                h.validate_moments(f)


TEST_ARTIFACTS = Path(__file__).resolve().parents[2]/'artifacts'


def self_test(artifacts, out):
    global TEST_ARTIFACTS
    artifacts = Path(artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    TEST_ARTIFACTS = artifacts
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    tests_seconds = time.perf_counter()-started
    # Sufficient moments remain synthetic. Inflate only the explicit exposure
    # column to exercise the fixed gate; do not misrepresent it as real duration.
    frame, games, _ = synthetic_panel(groups=8, series=6, frames_per_cell=12)
    frame['seconds'] = h.MIN_MINUTES*60
    frame.to_parquet(artifacts/'synthetic_frame_moments.parquet', index=False)
    games.to_parquet(artifacts/'synthetic_comeback_games.parquet', index=False)
    clock = time.perf_counter()
    report = h.inference(frame, games, bootstrap=3)
    for value in report['comparisons'].values():
        value['finding'] = False
    report.update(mode='synthetic_self_test', empirical_result=False,
                  caveat='Synthetic exposure inflated explicitly to exercise eligibility; never empirical evidence',
                  tests={'run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                         'elapsed_seconds': tests_seconds},
                  timings_seconds={'synthetic_inference': time.perf_counter()-clock,
                                   'total': time.perf_counter()-started})
    h.atomic_json(out, report)
    print(json.dumps({'tests': report['tests'], 'timings_seconds': report['timings_seconds'], 'out': str(out)}))
