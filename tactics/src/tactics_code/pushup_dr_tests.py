"""Data-free contracts for the P4 movement-initiation design.

These fixtures exercise measurement, train-only freezing, and the fitted AIPW
pipeline. They are software calibration checks, never replay research results.
"""
from __future__ import annotations

import json
import time
import numpy as np
import pandas as pd


def _measurement_checks(dr):
    t = np.arange(0., 2.01, .1)
    players = np.zeros((len(t), 6, 8), dtype=float)
    players[:, :, 7] = 0.
    players[:, 0, 1] = -1000 + 700*t
    players[:, 1, 1] = -500 - 700*t
    players[:, 2, 1] = 800
    players[:, 3:, 1] = 1000
    a = {'time': t, 'players': players, 'ball': np.zeros((len(t), 6)),
         'segment': np.zeros(len(t), dtype=int), 'live': np.ones(len(t), bool)}
    replay = {'replay_id': 'measurement', 'observed_start_time': 0., 'observed_end_time': 30.,
              'terminal_verified': False, 'terminal_time': None,
              'gap_start_times': '[]', 'gap_end_times': '[]'}
    goals = pd.DataFrame({'time': [], 'scoring_team': [], 'frame': []})
    measured = dr.initiation_measurement(a, np.array([0]), goals, replay)
    assert np.isclose(measured['displacement_1s'][0], 700.)
    assert dr.last_man_arrays(a)['last_man_index'][10] == 1
    # A goal exactly at t+1 belongs to the excluded exposure interval. The
    # sensitivity uses only the last pre-goal live position, never a reset.
    goals = pd.DataFrame({'time': [1., 11.], 'scoring_team': [1, 0], 'frame': [30, 330]})
    measured = dr.initiation_measurement(a, np.array([0]), goals, replay)
    assert measured['early_goal'][0] and np.isnan(measured['displacement_1s'][0])
    assert np.isclose(measured['displacement_including_early'][0], 630.)
    main = dr.event_labels(np.array([0.]), 0, goals, replay, followup_delay=1.)
    inclusive = dr.event_labels(np.array([0.]), 0, goals, replay,
                                followup_delay=1., include_window_goals=True)
    assert main['y10'][0] == 1 and inclusive['y10'][0] == 2
    # Open left at t, closed right at t+1; no later goal contaminates A.
    at_anchor = goals.copy()
    at_anchor.loc[0, 'time'] = 0.
    measured = dr.initiation_measurement(a, np.array([0]), at_anchor, replay)
    assert not measured['early_goal'][0] and np.isclose(measured['displacement_1s'][0], 700.)
    # A reset or missing original defender is an unknown measurement, not A=0.
    reset = dict(a, segment=np.where(t >= .5, 1, 0))
    assert np.isnan(dr.initiation_measurement(reset, np.array([0]), at_anchor, replay)['displacement_1s'][0])
    missing = dict(a, players=players.copy())
    missing['players'][10, 0, 1] = np.nan
    assert np.isnan(dr.initiation_measurement(missing, np.array([0]), at_anchor, replay)['displacement_1s'][0])
    demolished = dict(a, players=players.copy())
    demolished['players'][5, 0, 7] = 1.
    assert np.isnan(dr.initiation_measurement(demolished, np.array([0]), at_anchor, replay)['displacement_1s'][0])


def _fixture(dr, effect, seed=314159):
    """Confounded stochastic movement and multinomial outcomes in whole series."""
    rng = np.random.default_rng(seed)
    n_series, rows_per_series = 120, 80
    n = n_series*rows_per_series
    series = np.repeat(np.arange(n_series), rows_per_series)
    x = rng.choice([-1., 1.], n)
    df = pd.DataFrame(rng.normal(size=(n, len(dr.NUMERIC_FEATURES))), columns=dr.NUMERIC_FEATURES)
    df['ball_x'] = x
    df['ball_y'] = rng.uniform(-500, 500, n)
    df['remaining'] = rng.uniform(10, 180, n)
    df['score_diff'] = rng.choice([-1., 0., 1.], n)
    df['last_man_y_own'] = rng.uniform(1000, 3000, n)
    df['own0_y'] = df['last_man_y_own']-5120
    df['own1_y'] = df['own0_y']+500+rng.uniform(0, 500, n)
    df['own2_y'] = df['own1_y']+500+rng.uniform(0, 500, n)
    df['last_man_behind_ball'] = df['ball_y']-df['own0_y']
    df['last_man_id'] = rng.choice(['defender-a', 'defender-b', 'defender-c'], n)
    df['region'] = rng.choice(['region-a', 'region-b'], n)
    df['series_id'] = [f'synthetic-{s}' for s in series]
    df['split'] = np.where(series < 80, 'train', 'val')
    df['ball_bin'] = np.digitize(df['ball_y'], dr.BALL_EDGES[1:-1])
    df['baseline_goal_side'] = df['last_man_behind_ball'] > 0
    df['early_goal'] = False
    propensity = .5+.1*x
    arm = rng.binomial(1, propensity)
    df['displacement_1s'] = np.where(arm, dr.DEFAULT_DELTA+200, -100.)
    df['displacement_including_early'] = df['displacement_1s']
    p_for = .2+.06*x+effect*arm
    p_against = .2-.04*x-effect*arm/3
    u = rng.random(n)
    y = np.where(u < p_for, 1, np.where(u < p_for+p_against, 2, 0))
    for horizon in dr.HORIZONS:
        df[f'y{horizon}'] = y
        df[f'goal_id{horizon}'] = [f'synthetic-goal-{i}' if yi else '' for i, yi in enumerate(y)]
    df['ypast10'] = rng.choice([0., 1., 2.], n, p=[.8, .1, .1])
    return df


def _freeze_checks(dr, df):
    original, frozen = dr.freeze_initiation(df)
    mutated = df.copy()
    val = mutated['split'] == 'val'
    mutated.loc[val, 'last_man_y_own'] = -999999.
    mutated.loc[val, 'displacement_1s'] = 999999.
    mutated.loc[val, 'y10'] = 2.
    mutated.loc[val, 'region'] = 'validation-only-region'
    mutated.loc[val, 'last_man_id'] = 'validation-only-player'
    _, again = dr.freeze_initiation(mutated)
    assert frozen['bins'] == again['bins']
    train = df['split'].eq('train').to_numpy()
    first_x, first_names, first_regions = dr.feature_matrix(df, train, design='initiation')
    second_x, second_names, second_regions = dr.feature_matrix(mutated, train, design='initiation')
    assert first_names == second_names and first_regions == second_regions
    assert np.array_equal(first_x[train], second_x[train])
    assert not any('validation-only' in name for name in second_names)
    # Boundaries: delta is treated; delta/3 is ambiguous; retreat is control.
    boundary = df.iloc[:3].copy()
    boundary['last_man_y_own'] = 0.
    boundary['displacement_1s'] = [dr.DEFAULT_DELTA, dr.DEFAULT_DELTA/3, -1.]
    assigned, audit = dr.freeze_initiation(boundary, frozen=frozen)
    assert assigned['treatment'].iloc[0] == 1 and np.isnan(assigned['treatment'].iloc[1])
    assert assigned['treatment'].iloc[2] == 0 and audit['counts']['ambiguous_middle'] == 1
    return original


def _effect_check(dr, effect):
    df = _fixture(dr, effect)
    df = _freeze_checks(dr, df)
    retained = df[df['treatment'].notna()].reset_index(drop=True)
    pred, x, nuisance = dr.nuisance_predictions(retained, folds=3, seed=314159,
                                               iterations=30, design='initiation', workers=1)
    assert nuisance['validation_rows_used_in_fit'] == 0
    val = retained['split'].eq('val').to_numpy()
    result = dr.estimate_contrast(retained.loc[val].reset_index(drop=True), pred[val], x[val],
                                  nuisance['feature_names'], 'y10', .05, 1000, 314159,
                                  design='initiation')
    adjusted = result['adjusted']
    expected = {'difference_for': effect, 'difference_against': -effect/3,
                'difference_net_gd': effect*4/3}
    for name, truth in expected.items():
        point = adjusted[name]['estimate']
        ci = adjusted[name]['ci95']
        assert abs(point-truth) < .06, (name, point, truth)
        assert ci[0] <= truth <= ci[1], (name, ci, truth)
    if effect:
        assert adjusted['difference_for']['ci95'][0] > 0
        assert adjusted['difference_net_gd']['ci95'][0] > 0
    assert np.isclose(adjusted['difference_net_gd']['estimate'],
                      adjusted['difference_for']['estimate']-adjusted['difference_against']['estimate'])
    assert np.isclose(adjusted['advance_net_gd']['estimate'],
                      adjusted['advance_for']['estimate']-adjusted['advance_against']['estimate'])
    # The state design retains its structural failure even for perfect data.
    if not effect:
        state = dr.estimate_contrast(retained.loc[val].reset_index(drop=True), pred[val], x[val],
                                     nuisance['feature_names'], 'y10', .05, 100, 314159, design='state')
        assert state['causal_identification'] is False and state['structural_positivity'] is False
    return {'known_effect': expected, 'recovered': {
        name: {'estimate': float(adjusted[name]['estimate']),
               'ci95': np.asarray(adjusted[name]['ci95']).tolist()} for name in expected},
        'retained_train': int((~val).sum()), 'retained_val': int(val.sum())}


def _gate_checks(dr):
    """Positive and negative controls for the actual overlap decision."""
    n = 2000
    arm = np.tile([0, 1], n//2)
    y = np.tile([0, 0, 1, 1, 2, 2, 0, 0, 1, 1], n//10)
    df = pd.DataFrame({'series_id': np.repeat(np.arange(100), 20),
                       'treatment': arm, 'y10': y,
                       'goal_id10': [f'gate-goal-{i}' if yi else '' for i, yi in enumerate(y)]})
    prediction = np.column_stack([np.full(n, .5), np.tile([.4, .3, .3], (n, 8))])
    x = np.zeros((n, 1))
    result = dr.estimate_contrast(df, prediction, x, ['balanced_control'], 'y10', .05,
                                  50, 314159, design='initiation')
    assert result['causal_identification'] is True
    prediction[:, 0] = np.where(arm, .999, .001)
    failure = dr.estimate_contrast(df, prediction, x, ['balanced_control'], 'y10', .05,
                                   50, 314159, design='initiation')
    assert failure['causal_identification'] is False
    prediction[:, 0] = .5
    failure = dr.estimate_contrast(df, prediction, arm[:, None], ['nonoverlapping_control'],
                                   'y10', .05, 50, 314159, design='initiation')
    assert failure['causal_identification'] is False
    assert failure['balance']['undefined_smd_count'] == 1


def run_tests():
    from . import pushup_dr as dr
    started = time.perf_counter()
    _measurement_checks(dr)
    _gate_checks(dr)
    result = {'known_initiation_effect': _effect_check(dr, .12),
              'null_initiation_effect': _effect_check(dr, 0.)}
    result['elapsed_seconds'] = time.perf_counter()-started
    result['checks'] = ['fixed identity despite defender switch', 'landmark goal endpoints',
                        'early-goal truncation', 'unknown treatment not control',
                        'TRAIN median/category invariance', 'treatment threshold boundaries',
                        'full fitted AIPW known effect recovery', 'null confidence interval covers zero',
                        'joint net-GD arithmetic', 'C2 structural gate remains false',
                        'actual overlap gates pass and fail', 'undefined SMD fails balance']
    print(json.dumps({'initiation_self_test': 'passed', **result}))
    return result
