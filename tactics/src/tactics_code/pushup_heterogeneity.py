"""P6.3: team and last-man-player heterogeneity; development seasons only.

Two separately fitted specifications, each with correlated random intercept and
late:trailing slope. All valid frames enter the Gaussian likelihood through
exact sufficient statistics, not through an unweighted mean-response model.
Whole-series bootstrap refits both season-specific and pooled-training models.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tempfile
import time
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from statsmodels.regression.mixed_linear_model import MixedLM, MixedLMParams
import statsmodels

from .common import atomic_json
from .data import parsed_json, roster_key
from .pressure import last_man_arrays
from .screen import (ALLOWED_SEASONS, TRAIN_SEASONS, VAL_SEASON, REQUIRED,
                     guard_path, metadata_inventory, read_slice, unpack_shard,
                     replicate_map)
from .style_retrieval import check_rows

BOOTSTRAP, SEED, MAXITER = 2000, 42, 200
LATE_SECONDS, REGULATION_MAX, MIN_MINUTES = 60., 300., 20.
COHORTS = ('train',) + ALLOWED_SEASONS
GROUPS = ('roster_id', 'player_id')
TERMS = ('Intercept', 'late', 'trailing', 'late:trailing')
KEYS = ['season', 'split', 'series_id', 'roster_id', 'player_id', 'late', 'trailing']
SUMS = ['n', 'sy', 'sy2', 'seconds']
GAME_COLUMNS = ['season', 'split', 'series_id', 'replay_id', 'roster_id', 'player_id', 'win']


def identities(meta):
    check_rows(pd.DataFrame([meta]))
    ids = parsed_json(meta.get('player_ids'), [])
    if len(ids) != 6 or any(not isinstance(p, str) or not p for p in ids) or len(set(ids)) != 6:
        raise ValueError('Six distinct RQ4 stable player IDs required')
    if meta.get('roster_id') != roster_key(ids[:3]):
        raise ValueError('Roster ID must equal the canonical RQ4 roster hash')
    if meta.get('opponent_roster_id') != roster_key(ids[3:]):
        raise ValueError('Opponent roster ID inconsistent with player slots')
    return ids


def inventory(root):
    # Preflight all allowlisted metadata before the shared reader inspects ZIP
    # headers. Never enumerate the root's held-out season directories.
    root = guard_path(root)
    for season in ALLOWED_SEASONS:
        directory = guard_path(root / season)
        for path in sorted(directory.glob('compact-*.parquet')):
            frame = pd.read_parquet(guard_path(path))
            check_rows(frame)
            if not frame.season.eq(season).all():
                raise ValueError('Metadata directory/season mismatch')
            for row in frame.to_dict('records'):
                identities(row)
    pairs, audit = metadata_inventory(root)
    seen, series_seasons = set(), defaultdict(set)
    for pair in pairs:
        for row in pair:
            identities(row)
            key = (row['replay_id'], row['focal_team'])
            if key in seen:
                raise ValueError('Duplicate replay perspective')
            seen.add(key)
            series_seasons[row['series_id']].add(row['season'])
            start, stop = int(row['start']), int(row['stop'])
            if not 0 <= start < stop:
                raise ValueError('Invalid compact offsets')
            for channel in REQUIRED:
                if stop > audit['schema'][row['_shard']][channel]['shape'][0]:
                    raise ValueError('Compact offset exceeds array')
        if parsed_json(pair[0]['player_ids'])[:3] != parsed_json(pair[1]['player_ids'])[3:]:
            raise ValueError('Focal views disagree on player ordering')
    if any(len(s) != 1 for s in series_seasons.values()):
        raise ValueError('Series spans seasons')
    return pairs, audit


def validate_events(events):
    required = {'season', 'series_id', 'replay_id', 'validated', 'terminal_verified',
                'header_goals_0', 'header_goals_1'}
    if not required <= set(events):
        raise ValueError('Certified replay_events schema required')
    if not events.season.isin(ALLOWED_SEASONS).all():
        raise ValueError('Forbidden event season; held-out data are guarded')
    if 'split' in events:
        check_rows(events)
    if events.replay_id.duplicated().any():
        raise ValueError('Duplicate replay event certificate')
    for col in ('validated', 'terminal_verified'):
        if not events[col].isin([True, False]).all():
            raise ValueError('Event certification flags must be known booleans')


def summarize_replay(meta, arrays, event=None):
    """Keep exact frame moments; clock and exposure use the compact's sampling.

    All regulation frames with 0 < clock <= regulation maximum, score +/-1,
    known live segment and a unique valid last man. Tied last-man depth is
    excluded from BOTH specifications so the observation population is shared.
    """
    ids = identities(meta)
    a = arrays
    t, rem = np.asarray(a['time'], float), np.asarray(a['remaining'], float)
    score = np.asarray(a['score_diff'], float)
    if not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Compact time must be finite and strictly increasing')
    fps = float(meta['fps'])
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError('Invalid compact fps')
    depth = last_man_arrays(a)
    ys = np.asarray(a['players'])[:, :3, 1]
    unique = (ys == np.min(ys, axis=1)[:, None]).sum(axis=1) == 1
    valid = (np.asarray(a['live'], bool) & (a['segment'] >= 0) &
             (a['overtime'] == 0) & (rem > 0) & (rem <= REGULATION_MAX) &
             np.isin(score, [-1, 1]) & depth['last_man_valid'] & unique)
    selected = np.flatnonzero(valid)
    base = {k: meta[k] for k in ('season', 'split', 'series_id', 'roster_id')}
    f = pd.DataFrame({**base, 'player_id': np.asarray(ids)[depth['last_man_index'][selected]],
                      'late': (rem[selected] <= LATE_SECONDS).astype(int),
                      'trailing': (score[selected] < 0).astype(int),
                      'y': depth['last_man_y_own'][selected]})
    f['n'], f['sy'], f['sy2'], f['seconds'] = 1, f.y, f.y**2, 1/fps
    moments = f.groupby(KEYS, sort=True)[SUMS].sum().reset_index()
    audit = Counter(frames=len(t), valid_frames=len(selected),
                    tied_last_man_frames=int((depth['last_man_valid'] & ~unique).sum()))
    games = []
    # First observed live sample on the 60-second clock tick; never use a
    # post-threshold nearest sample. A small pre-threshold fractional sample
    # is admissible only within one nominal sample interval.
    snap = np.flatnonzero(np.asarray(a['live'], bool) & (a['segment'] >= 0) &
                         (a['overtime'] == 0) & (rem >= LATE_SECONDS) &
                         (rem <= LATE_SECONDS + 1/fps + 1e-6))
    exact = snap[np.isclose(rem[snap], LATE_SECONDS, rtol=0, atol=1e-6)]
    if len(exact):
        snap = exact
    if not len(snap):
        audit['comeback_missing_clock_snapshot'] += 1
    elif not np.isfinite(score[snap]).all() or len(np.unique(score[snap])) != 1:
        audit['comeback_ambiguous_clock_score'] += 1
    elif score[snap[0]] != -1:
        audit['comeback_not_trailing_by_one'] += 1
    elif event is None:
        audit['comeback_missing_certificate'] += 1
    else:
        if event['season'] != meta['season'] or event['series_id'] != meta['series_id']:
            raise ValueError('Compact/event grouping mismatch')
        totals = np.array([event['header_goals_0'], event['header_goals_1']], float)
        if (not event['validated'] or not event['terminal_verified'] or
                not np.isfinite(totals).all() or (totals < 0).any() or
                not np.equal(totals, np.floor(totals)).all() or totals[0] == totals[1]):
            audit['comeback_uncertified_final_score'] += 1
        else:
            i = int(snap[0])
            player = ids[int(depth['last_man_index'][i])] if depth['last_man_valid'][i] and unique[i] else None
            games.append({**base, 'replay_id': meta['replay_id'], 'player_id': player,
                          'win': int(np.argmax(totals) == int(meta['focal_team']))})
            audit['comeback_team_games'] += 1
            audit['comeback_player_games'] += int(player is not None)
    return moments, games, audit


def build_tables(pairs, events, artifacts, scratch=None, smoke=False):
    validate_events(events)
    lookup = events.set_index('replay_id').to_dict('index')
    by_shard = defaultdict(list)
    for pair in pairs:
        for meta in pair:
            by_shard[meta['_shard']].append(meta)
    frames, games, audit = [], [], Counter()
    for shard, records in sorted(by_shard.items()):
        with tempfile.TemporaryDirectory(prefix='p63-', dir=scratch or artifacts) as tmp:
            arrays = None
            if not smoke:
                directory = Path(unpack_shard(guard_path(shard), Path(tmp)))
                arrays = {key: np.load(directory / (key + '.npy'), mmap_mode='r', allow_pickle=False)
                          for key in REQUIRED}
            for meta in records:
                identities(meta)
                a = read_slice(meta) if smoke else {
                    key: value[int(meta['start']):int(meta['stop'])] for key, value in arrays.items()}
                frame, rows, counts = summarize_replay(meta, a, lookup.get(meta['replay_id']))
                frames.append(frame)
                games.extend(rows)
                audit.update(counts)
            del arrays
    moments = pd.concat(frames, ignore_index=True).groupby(KEYS, sort=True)[SUMS].sum().reset_index()
    game_table = pd.DataFrame(games, columns=GAME_COLUMNS)
    if game_table.duplicated(['replay_id', 'roster_id']).any():
        raise ValueError('Duplicate comeback game')
    return moments, game_table, dict(audit)


def validate_moments(frame):
    check_rows(frame)
    if frame.empty:
        raise ValueError('No usable observations')
    if not set(KEYS + SUMS) <= set(frame):
        raise ValueError('Missing moment columns')
    if frame[KEYS].isna().any().any() or not frame[['late', 'trailing']].isin([0, 1]).all().all():
        raise ValueError('Unknown identity/context')
    if not np.isfinite(frame[SUMS]).all().all() or (frame.n <= 0).any() or (frame.seconds <= 0).any():
        raise ValueError('Invalid frame moments')
    if not np.equal(frame.n, np.floor(frame.n)).all():
        raise ValueError('Frame counts must be integers')
    if (frame.sy2 - frame.sy**2/frame.n < -1e-6*np.maximum(1, frame.sy2)).any():
        raise ValueError('Negative within-cell sum of squares')
    if frame.groupby('series_id').season.nunique().max() > 1:
        raise ValueError('Series spans seasons')


def compressed_model(frame, group):
    """Exact orthogonal compression of constant X/Z cells for statsmodels.

    In each cell retain sqrt(n)*mean(y), sqrt(n)*X, sqrt(n)*Z. All
    orthogonal residual coordinates have X=Z=0; their squared norm is SSE.
    Retain its square root as one residual-only row per group. The discarded
    coordinates contribute only to the Gaussian observation count. Restoring
    nobs/n_totobs therefore preserves ML/REML likelihood, scores and BLUPs.
    This uses an internal statsmodels count attribute and is parity-tested.
    """
    validate_moments(frame)
    cells = frame.groupby([group, 'late', 'trailing'], sort=True)[SUMS].sum().reset_index()
    design = np.column_stack([np.ones(len(cells)), cells.late, cells.trailing,
                              cells.late*cells.trailing])
    if np.linalg.matrix_rank(design) != len(TERMS) or cells[group].nunique() < 3:
        raise ValueError('Need all design cells and independent identity groups')
    root = np.sqrt(cells.n.to_numpy(float))
    x, z = design*root[:, None], design[:, [0, 3]]*root[:, None]
    y = cells.sy.to_numpy(float)/root
    residual = np.maximum(0., cells.sy2 - cells.sy**2/cells.n)
    sse = residual.groupby(cells[group], sort=True).sum()
    model = MixedLM(np.r_[y, np.sqrt(sse.to_numpy())],
                    np.vstack([x, np.zeros((len(sse), x.shape[1]))]),
                    groups=np.r_[cells[group].to_numpy(), sse.index.to_numpy()],
                    exog_re=np.vstack([z, np.zeros((len(sse), z.shape[1]))]))
    model.nobs = model.n_totobs = int(cells.n.sum())
    return model


def cr1_fixed(frame, group, fitted):
    """Series score sandwich for GLS fixed coefficients, covariance held fitted.

    Marginal V couples series inside an identity. Compute the full-group
    correction first, then assign row scores to their original whole series.
    Variance-component estimation uncertainty is covered by the refit bootstrap.
    """
    beta, sigma, cov = np.asarray(fitted.fe_params), fitted.scale, np.asarray(fitted.cov_re)
    bread = np.zeros((len(TERMS), len(TERMS)))
    scores = defaultdict(lambda: np.zeros(len(TERMS)))
    for _, f in frame.groupby(group):
        x = np.column_stack([np.ones(len(f)), f.late, f.trailing, f.late*f.trailing])
        z = x[:, [0, 3]]
        n, sy = f.n.to_numpy(float), f.sy.to_numpy(float)
        middle = np.linalg.inv(np.linalg.inv(cov) + z.T @ (n[:, None]*z)/sigma)
        cross = x.T @ (n[:, None]*z)/sigma
        bread += x.T @ (n[:, None]*x)/sigma - cross @ middle @ cross.T
        adjustment = middle @ (z.T @ (sy - n*(x@beta))/sigma)
        row_score = x*((sy - n*(x@beta) - n*(z@adjustment))/sigma)[:, None]
        for series, values in zip(f.series_id, row_score):
            scores[series] += values
    g, n, p = len(scores), int(frame.n.sum()), len(TERMS)
    if g <= 1 or n <= p:
        return {'status': 'not_estimable'}
    s = np.stack(list(scores.values()))
    inv = np.linalg.inv(bread)
    covariance = inv @ (s.T@s) @ inv * (g/(g-1))*((n-1)/(n-p))
    return {'status': 'fit', 'n_series': g, 'se': dict(zip(TERMS, np.sqrt(np.maximum(0, np.diag(covariance))))),
            'covariance': covariance.tolist(), 'variance_components_held_fitted': True}


def fit_model(frame, group, maxiter=MAXITER, diagnostics=True):
    started = time.perf_counter()
    attempts = []
    try:
        model = compressed_model(frame, group)
    except (ValueError, np.linalg.LinAlgError) as exc:
        return {'status': 'not_estimable', 'reason': str(exc), 'slopes': {}, 'attempts': []}
    # Same correlated specification first; a diagonal covariance is explicitly
    # a fallback and cannot support the registered primary stability finding.
    for diagonal in (False, True):
        free = None
        if diagonal:
            free = MixedLMParams.from_components(fe_params=np.ones(model.k_fe), cov_re=np.eye(model.k_re))
        for method in ('lbfgs', 'bfgs', 'powell'):
            if diagonal and method == 'powell':
                continue  # Powell does not honor the free mask.
            try:
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter('always')
                    fitted = model.fit(reml=False, method=method, maxiter=maxiter,
                                       free=free, disp=False, full_output=True)
                warning_text = sorted({str(w.message) for w in captured})
                eigen = np.linalg.eigvalsh(fitted.cov_re)
                acceptable = (fitted.converged and np.isfinite(fitted.fe_params).all() and
                              np.isfinite(fitted.scale) and fitted.scale > 0 and
                              np.isfinite(eigen).all() and eigen.min() > 1e-10)
                attempts.append({'method': method, 'diagonal': diagonal,
                                 'converged': bool(fitted.converged), 'accepted': bool(acceptable),
                                 'warnings': warning_text})
                if not acceptable:
                    continue
                effects = fitted.random_effects
                slopes = {str(identity): float(np.asarray(values)[1]) for identity, values in effects.items()}
                if not np.isfinite(list(slopes.values())).all():
                    raise ValueError('Nonfinite BLUPs')
                report = {'status': 'fallback_diagonal' if diagonal else 'fit', 'slopes': slopes,
                          'fixed': dict(zip(TERMS, map(float, fitted.fe_params))),
                          'total_slopes': {k: v + float(fitted.fe_params[3]) for k, v in slopes.items()},
                          'covariance': np.asarray(fitted.cov_re).tolist(), 'residual_variance': float(fitted.scale),
                          'log_likelihood': float(fitted.llf), 'n_frames': int(frame.n.sum()),
                          'n_groups': len(slopes), 'attempts': attempts,
                          'elapsed_seconds': time.perf_counter()-started}
                if diagnostics:
                    try:
                        report['cr1_fixed'] = cr1_fixed(frame, group, fitted)
                    except np.linalg.LinAlgError as exc:
                        report['cr1_fixed'] = {'status': 'not_estimable', 'reason': str(exc)}
                return report
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                attempts.append({'method': method, 'diagonal': diagonal, 'error': str(exc)})
    return {'status': 'not_estimable', 'reason': 'MixedLM attempts failed; no OLS or unshrunk substitute',
            'slopes': {}, 'attempts': attempts, 'elapsed_seconds': time.perf_counter()-started}


def cohort(frame, name):
    return frame.loc[frame.split.eq('train') if name == 'train' else frame.season.eq(name)]


def fit_all(frame, maxiter=MAXITER, diagnostics=True):
    return {f'{name}/{group}': fit_model(cohort(frame, name), group, maxiter, diagnostics)
            for name in COHORTS for group in GROUPS}


def rho(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or not np.isfinite(x).all() or not np.isfinite(y).all() or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    return float(spearmanr(x, y).statistic)


def compare(frame, games, fits, fixed_ids=None):
    """Always emit comeback associations, independently of stability results."""
    results = {}
    for group in GROUPS:
        for left in ('train',) + TRAIN_SEASONS:
            key = f'stability/{left}/{VAL_SEASON}/{group}'
            exposure = []
            for name in (left, VAL_SEASON):
                part = cohort(frame, name)
                exposure.append(part.loc[part.late.eq(1) & part.trailing.eq(1)].groupby(group).seconds.sum()/60)
            eligible = sorted(set(exposure[0][exposure[0] >= MIN_MINUTES].index) &
                              set(exposure[1][exposure[1] >= MIN_MINUTES].index))
            ids = eligible if fixed_ids is None else fixed_ids[key]
            a, b = fits[f'{left}/{group}'], fits[f'{VAL_SEASON}/{group}']
            available = all(i in a['slopes'] and i in b['slopes'] for i in ids)
            value = rho([a['slopes'][i] for i in ids], [b['slopes'][i] for i in ids]) if available else None
            results[key] = {'rho': value, 'eligible_ids': ids, 'n_units': len(ids),
                            'trailing_late_minutes': {
                                str(i): {left: float(exposure[0].get(i, 0)),
                                         VAL_SEASON: float(exposure[1].get(i, 0))} for i in ids},
                            'model_statuses': [a['status'], b['status']],
                            'status': 'fit' if value is not None else 'not_estimable'}
        for name in COHORTS:
            key = f'comeback/{name}/{group}'
            f = fits[f'{name}/{group}']
            rates = cohort(games, name).dropna(subset=[group]).groupby(group).win.agg(['mean', 'size', 'sum'])
            eligible = sorted(set(f['slopes']) & set(rates.index))
            ids = eligible if fixed_ids is None else fixed_ids[key]
            available = all(i in f['slopes'] and i in rates.index for i in ids)
            value = rho([f['slopes'][i] for i in ids], rates.loc[ids, 'mean']) if available else None
            results[key] = {'rho': value, 'eligible_ids': ids, 'n_units': len(ids),
                            'model_statuses': [f['status']], 'reported_regardless': True,
                            'rates': {str(i): {'wins': int(rates.loc[i, 'sum']), 'games': int(rates.loc[i, 'size']),
                                              'rate': float(rates.loc[i, 'mean'])} for i in ids if i in rates.index},
                            'status': 'fit' if value is not None else 'not_estimable'}
    return results


def series_draw(frame, games, rng):
    """Same series multiplicity for both focal teams, models and game outcomes."""
    moments, outcomes = [], []
    for season in ALLOWED_SEASONS:
        f, g = cohort(frame, season), cohort(games, season)
        ids = sorted(set(f.series_id) | set(g.series_id))
        if not ids:
            continue
        counts = Counter(rng.choice(ids, size=len(ids), replace=True))
        # Multiplying sufficient moments is exactly repeated-series sampling.
        take = f.series_id.map(counts).fillna(0).to_numpy(int)
        block = f.loc[take > 0].copy()
        block[SUMS] = block[SUMS].mul(take[take > 0], axis=0)
        moments.append(block)
        for identity, count in counts.items():
            for _ in range(count):
                outcomes.append(g.loc[g.series_id.eq(identity)])
    return (pd.concat(moments, ignore_index=True) if moments else frame.iloc[:0].copy(),
            pd.concat(outcomes, ignore_index=True) if outcomes else games.iloc[:0].copy())


def inference(frame, games, bootstrap=BOOTSTRAP, seed=SEED, workers=1, maxiter=MAXITER):
    validate_moments(frame)
    check_rows(games)
    if not set(GAME_COLUMNS) <= set(games) or not games.win.isin([0, 1]).all():
        raise ValueError('Invalid comeback outcomes')
    combined = pd.concat([frame[['series_id', 'season']], games[['series_id', 'season']]])
    if combined.groupby('series_id').season.nunique().max() > 1:
        raise ValueError('Game and frame series cross seasons')
    fits = fit_all(frame, maxiter)
    comparisons = compare(frame, games, fits)
    fixed_ids = {key: value['eligible_ids'] for key, value in comparisons.items()}

    def replicate(rng):
        f, g = series_draw(frame, games, rng)
        models = fit_all(f, maxiter, diagnostics=False)
        correlations = compare(f, g, models, fixed_ids)
        return {'rho': {k: (v['rho'] if all(s == 'fit' for s in v['model_statuses']) else None)
                        for k, v in correlations.items()},
                'fixed': {k: v.get('fixed') if v['status'] == 'fit' else None for k, v in models.items()},
                'fit_statuses': dict(Counter(v['status'] for v in models.values()))}

    draws = replicate_map(replicate, bootstrap, seed, 'P6.3', 'series', workers,
                          progress=lambda **x: print(json.dumps(x), flush=True)) if bootstrap else []
    for key, comparison in comparisons.items():
        valid = [draw['rho'][key] for draw in draws if draw['rho'][key] is not None]
        ci = np.quantile(valid, [.025, .975]).tolist() if len(valid) >= 2 else [None, None]
        complete = bootstrap >= 2 and len(valid) == bootstrap
        comparison.update(ci95=ci, bootstrap_successful=len(valid), bootstrap_requested=bootstrap,
                          bootstrap_complete=complete,
                          finding=bool(key.startswith('stability/') and bootstrap == BOOTSTRAP and
                                       complete and ci[0] > 0 and
                                       comparison['rho'] is not None and
                                       all(s == 'fit' for s in comparison['model_statuses'])))
        if not complete:
            comparison['interval_status'] = 'incomplete_or_unavailable; numerical interval only'
    for key, fit in fits.items():
        valid = [d['fixed'][key] for d in draws if d['fixed'][key] is not None]
        fit['fixed_bootstrap_ci95'] = {term: np.quantile([v[term] for v in valid], [.025, .975]).tolist()
                                      for term in TERMS} if len(valid) >= 2 else {}
        fit['fixed_bootstrap_successful'] = len(valid)
    counts = Counter()
    for draw in draws:
        counts.update(draw['fit_statuses'])
    return {'fits': fits, 'comparisons': comparisons,
            'bootstrap': {'requested': bootstrap, 'seed': seed, 'workers': workers,
                          'unit': 'whole series, stratified by season; all models refitted',
                          'eligibility': 'fixed from original sample; missing eligible identity invalidates draw',
                          'fit_status_counts': dict(counts)},
            'scope': {'train_seasons': TRAIN_SEASONS, 'validation_season': VAL_SEASON,
                      'held_out_opened': False, 'min_trailing_late_minutes_each_cohort': MIN_MINUTES},
            'methods': {'formula': 'last_man_y_own ~ late*trailing', 'random_formula': '1 + late:trailing',
                        'specifications': 'separate roster and last-man player models, not mutually adjusted',
                        'fit': 'Gaussian ML / statsmodels MixedLM, exact frame-moment compression',
                        'primary_stability': 'pooled train versus validation; individual train-season comparisons also reported',
                        'comeback_player': 'player who is uniquely last man at the clock snapshot',
                        'population': 'live regulation, known segment, unique valid last man, exact score +/-1',
                        'clock_seconds': {'minimum_exclusive': 0, 'maximum_inclusive': REGULATION_MAX,
                                          'late_maximum_inclusive': LATE_SECONDS},
                        'exposure': 'valid sample count / compact fps; no elapsed-gap interpolation',
                        'association_only': True, 'statsmodels_version': statsmodels.__version__}}


def file_record(path):
    path = guard_path(path)
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path)
    parser.add_argument('--replay-events', type=Path, help='Certified P4 replay_events.parquet')
    parser.add_argument('--data-root', type=Path, help='Build certificates from these local native frames if needed')
    parser.add_argument('--state-map', type=Path, default=Path('state_map_rlcs.json'))
    parser.add_argument('--artifacts', type=Path, default=Path('artifacts/p6-heterogeneity'))
    parser.add_argument('--out', type=Path, default=Path('results/pushup_heterogeneity.json'))
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--max-replays', type=int)
    parser.add_argument('--bootstrap', type=int, default=BOOTSTRAP)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--maxiter', type=int, default=MAXITER)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        import importlib.util
        path = Path(__file__).resolve().parents[1] / 'tests/test_pushup_heterogeneity.py'
        spec = importlib.util.spec_from_file_location('test_pushup_heterogeneity', path)
        test = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test)
        test.self_test(args.artifacts, args.out)
        return
    if args.compact is None or not (args.replay_events or args.data_root):
        parser.error('--compact and either --replay-events or --data-root are required')
    if min(args.workers, args.maxiter) < 1 or args.bootstrap < 0 or (args.max_replays is not None and args.max_replays < 1):
        parser.error('Invalid count argument')
    started = time.perf_counter()
    artifacts = guard_path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    if args.scratch:
        guard_path(args.scratch).mkdir(parents=True, exist_ok=True)
    compact = guard_path(args.compact)
    for target in (artifacts, guard_path(args.out)):
        if target.resolve() == compact.resolve() or compact.resolve() in target.resolve().parents:
            raise ValueError('Outputs must not modify compact inputs')
    pairs, audit = inventory(compact)
    available = len(pairs)
    if args.max_replays:
        # Round-robin seasons for a diagnostic smoke; never infer from smoke.
        buckets = {s: [p for p in pairs if p[0]['season'] == s] for s in ALLOWED_SEASONS}
        pairs = []
        while len(pairs) < args.max_replays and any(buckets.values()):
            for season in ALLOWED_SEASONS:
                if buckets[season] and len(pairs) < args.max_replays:
                    pairs.append(buckets[season].pop(0))
    inventory_seconds = time.perf_counter()-started
    clock = time.perf_counter()
    selected = [row for pair in pairs for row in pair]
    if args.replay_events:
        event_path = guard_path(args.replay_events)
        events = pd.read_parquet(event_path)
    else:
        from .events import build_events
        _, events = build_events(selected, artifacts, guard_path(args.data_root), guard_path(args.state_map))
        event_path = artifacts / 'replay_events.parquet'
    validate_events(events)
    event_seconds = time.perf_counter()-clock
    clock = time.perf_counter()
    moments, games, extraction_audit = build_tables(pairs, events, artifacts, args.scratch, bool(args.max_replays))
    moments.to_parquet(artifacts / 'frame_moments.parquet', index=False)
    games.to_parquet(artifacts / 'comeback_games.parquet', index=False)
    extraction_seconds = time.perf_counter()-clock
    clock = time.perf_counter()
    result = inference(moments, games, args.bootstrap, args.seed, args.workers, args.maxiter)
    inference_seconds = time.perf_counter()-clock
    if args.max_replays or args.bootstrap != BOOTSTRAP:
        for value in result['comparisons'].values():
            value['finding'] = False
    result.update(mode='smoke' if args.max_replays else 'full', empirical_result=True,
                  registered_run=not args.max_replays and args.bootstrap == BOOTSTRAP,
                  source={'compact': str(compact), 'replay_events': file_record(event_path),
                          'metadata': [file_record(Path(p).with_suffix('.parquet')) for p in sorted(audit['schema'])],
                          'compact_files': [{'path': p, 'bytes': Path(p).stat().st_size,
                                             'mtime_ns': Path(p).stat().st_mtime_ns} for p in sorted(audit['schema'])],
                          'code': file_record(Path(__file__)), 'available_replays': available,
                          'selected_replays': sorted({r['replay_id'] for r in selected}),
                          'complete_series_certified': audit['complete_series_certified']},
                  extraction_audit=extraction_audit,
                  timings_seconds={'inventory': inventory_seconds, 'events': event_seconds,
                                   'extraction': extraction_seconds, 'inference': inference_seconds,
                                   'total': time.perf_counter()-started})
    atomic_json(guard_path(args.out), result)
    print(json.dumps({'output': str(args.out), 'timings_seconds': result['timings_seconds']}))


if __name__ == '__main__':
    main()
