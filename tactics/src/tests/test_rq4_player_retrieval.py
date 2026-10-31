"""Independent RQ4 player retrieval tests; no real RLCS inputs required."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from tactics_code import style_retrieval as sr


def planted(null=False, n=20):
    rng = np.random.default_rng(123)
    features = [f'f_{j}' for j in range(n)]
    rows, metadata = [], []
    offsets = rng.permutation(n)
    for split, season in [('train', 'rlcs-2024'), ('val', 'rlcs-2025')]:
        for series in range(n):
            for game in range(2):
                for identity in range(n):
                    # Balanced, independently shuffled query identity assignments;
                    # every identity sees every prototype once across val series.
                    source = (identity+offsets[series]) % n if null and split == 'val' else identity
                    vector = np.eye(n)[source]*4
                    if not null:
                        vector += rng.normal(0, .01, n)
                    pid = f'p{identity:02d}'
                    meta = dict(season=season, split=split, region='EU',
                                replay_id=f'{split}-{series}-{game}-{identity}',
                                series_id=f'{split}-{series}', roster_id=f'{split}-roster-{identity}',
                                player_ids=[pid, f'{split}-dummy-a-{identity}', f'{split}-dummy-b-{identity}'])
                    metadata.append(meta)
                    rows.append({**meta, 'identity_id': pid, **dict(zip(features, vector))})
    frame = pd.DataFrame(rows)
    return frame[frame.split == 'train'].copy(), frame[frame.split == 'val'].copy(), features, metadata


def test_planted_identity_and_roster_control_recovered():
    train, val, features, metadata = planted()
    result = sr.evaluate_retrieval(train, val, features, metadata, permutations=199, bootstrap=199)
    assert result['n_gallery'] == 20
    for analysis in ['primary', 'team_context_control']:
        for metric in ['top1', 'top5', 'mrr']:
            d = result[analysis]['metrics'][metric]
            assert d['estimate'] > .98
            assert d['p_value'] <= .01
            assert d['ci95'] == [1., 1.]
    assert result['primary']['metrics']['top1']['null_mean'] == pytest.approx(.05, abs=.02)


def test_label_shuffled_synthetic_is_exact_chance():
    result = sr.evaluate_retrieval(*planted(null=True), permutations=99, bootstrap=99)
    chance = {'top1': 1/20, 'top5': 5/20, 'mrr': np.mean(1/np.arange(1, 21))}
    for analysis in ['primary', 'team_context_control']:
        for metric, value in chance.items():
            d = result[analysis]['metrics'][metric]
            assert d['estimate'] == pytest.approx(value)
            assert d['null_mean'] == pytest.approx(value)
            assert d['p_value'] > .05


def test_twenty_game_gate_never_pools_training_seasons():
    train, val, _, _ = planted()
    assert len(sr.eligible_players(train, val)) == 20
    train = train.groupby('identity_id').head(30).copy()
    train.loc[train.groupby('identity_id').cumcount() >= 15, 'season'] = 'rlcs-22-23'
    assert sr.eligible_players(train, val) == []
    train['season'] = 'rlcs-2024'
    assert len(sr.eligible_players(train, val)) == 20
    assert sr.eligible_players(train, val.groupby('identity_id').head(19)) == []
    # Distinct games, not duplicated rows.
    few = val.groupby('identity_id').head(10)
    assert sr.eligible_players(train, pd.concat([few]*4)) == []


def test_scaling_uses_train_only_and_duplicate_games_do_not_weight_it():
    train, val, features, metadata = planted()
    model = sr.fit_gallery(train, features)
    repeated = sr.fit_gallery(pd.concat([train, train.iloc[:40]]), features)
    np.testing.assert_allclose(model['mean'], repeated['mean'])
    np.testing.assert_allclose(model['vectors'], repeated['vectors'])
    val[features] += 1e8
    result = sr.evaluate_retrieval(train, val, features, metadata, permutations=0, bootstrap=0)
    np.testing.assert_allclose(result['scaling']['mean'], model['mean'])
    np.testing.assert_allclose(result['scaling']['scale'], model['scale'])


def test_team_control_excludes_same_roster_target_and_teammates():
    train, val, features, metadata = planted()
    # p00 stayed on its train roster, so its target is absent in the control.
    val.loc[val.identity_id == 'p00', 'roster_id'] = 'train-roster-0'
    for meta in metadata:
        if meta['split'] == 'val' and meta['player_ids'][0] == 'p00':
            meta['roster_id'] = 'train-roster-0'
        # p01 and p02 are known former teammates; each must lose one candidate.
        if meta['split'] == 'train' and meta['player_ids'][0] == 'p01':
            meta['player_ids'][1] = 'p02'
    result = sr.evaluate_retrieval(train, val, features, metadata, permutations=19, bootstrap=19)
    control = result['team_context_control']
    assert control['excluded_true_identity'] == 20
    assert control['queries_evaluated'] == 380
    assert control['candidate_count']['min'] == 19
    assert control['metrics']['top1']['estimate'] == 1


def test_null_permutations_never_cross_region():
    # Perfectly identifiable region, no within-region identity signal: ties
    # average out. A global permutation would spuriously lower this null.
    d = np.array([[0., 0., 10., 10.]]*2 + [[10., 10., 0., 0.]]*2)
    result = sr.infer(d, np.arange(4), np.ones((4, 4), bool), ['s']*4,
                      np.array(['EU', 'EU', 'NA', 'NA']), 99, 9, 42)
    assert result['metrics']['top1']['estimate'] == .5
    assert result['metrics']['top1']['null_mean'] == .5
    assert result['metrics']['top1']['p_value'] == 1


def test_bootstrap_keeps_complete_series_together():
    d = np.array([[0., 1.]]*50 + [[1., 0.]]*50)
    result = sr.infer(d, np.zeros(100, int), np.ones((100, 2), bool),
                      ['a']*50 + ['b']*50, np.array(['EU', 'EU']), 0, 999, 42)
    assert result['metrics']['top1']['estimate'] == .5
    assert result['metrics']['top1']['ci95'] == [0., 1.]


def test_2026_guard_precedes_read_and_rejects_symlinks(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Reader called before the 2026 guard')
    monkeypatch.setattr(sr, 'metadata_inventory', forbidden)
    with pytest.raises(ValueError, match='2026'):
        sr.inventory(tmp_path/'rlcs-2026')
    target = tmp_path/'rlcs-2026'
    target.mkdir()
    link = tmp_path/'allowed'
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='2026'):
        sr.inventory(link)
    train, val, features, metadata = planted()
    train.iloc[0, train.columns.get_loc('season')] = 'rlcs-2026'
    with pytest.raises(ValueError, match='2026'):
        sr.fit_gallery(train, features)
    val.iloc[0, val.columns.get_loc('season')] = 'rlcs-2026'
    with pytest.raises(ValueError, match='2026'):
        sr.eligible_players(train, val)


def test_player_features_slot_equivariance_and_boundary_safe_rates():
    n = 240
    p = np.zeros((n, 6, 8))
    p[:, :, 6] = 100
    p[:, :, 7] = np.nan
    p[:, :3, :3] = [[-1000, -1800, 17], [700, 900, 100], [2300, -700, 400]]
    p[:, :, 3] = 700
    flags = np.zeros((n, 6, 4))
    flags[120:, 0, 0] = 1  # boundary onset must not count
    a = dict(players=p, flags=flags, time=np.arange(n)/10., segment=np.repeat([0, 1], 120),
             live=np.ones(n, bool), ball=np.zeros((n, 6)), touch=np.full(n, -1),
             roles=np.tile([0, 1, 2], (n, 1)), role_uncertain=np.zeros(n, bool))
    meta = dict(season='rlcs-2025', split='val', series_id='s', replay_id='r',
                roster_id='r0', player_ids=[f'p{i}' for i in range(6)], region='EU', fps=10.)
    baseline = sr.game_features(meta, a)
    assert len(baseline) == 3
    assert baseline[0]['f_dodge_per_minute'] == 0
    assert baseline[0]['f_deepest_share'] == 1
    order = [2, 0, 1, 3, 4, 5]
    changed = dict(a, players=p[:, order], flags=flags[:, order], roles=a['roles'][:, order[:3]])
    permuted = sr.game_features(dict(meta, player_ids=[meta['player_ids'][i] for i in order]), changed)
    for old, new in zip(sorted(baseline, key=lambda r:r['identity_id']), sorted(permuted, key=lambda r:r['identity_id'])):
        for key in old:
            if key.startswith('f_'):
                assert old[key] == pytest.approx(new[key], nan_ok=True)


def test_staging_allowlist_and_full_slice_reader_agree(tmp_path):
    import json
    source = tmp_path/'source'
    source.mkdir()
    (source/'extraction.json').write_text(json.dumps({'state_map': {'state_decoding': 'per_replay_decoded'}}))
    n = 120
    arrays = dict(players=np.zeros((2*n, 6, 8)), ball=np.zeros((2*n, 6)),
                  flags=np.zeros((2*n, 6, 4)), roles=np.zeros((2*n, 3), dtype=np.int8),
                  role_uncertain=np.zeros(2*n, bool), touch=np.full(2*n, -1, dtype=np.int8),
                  time=np.tile(np.arange(n)/10., 2), frame=np.tile(np.arange(n)*3, 2),
                  segment=np.zeros(2*n, int), live=np.ones(2*n, bool),
                  remaining=np.full(2*n, 300.), overtime=np.zeros(2*n), score_diff=np.zeros(2*n))
    for season in sr.ALLOWED_SEASONS:
        directory = source/season
        directory.mkdir()
        path = directory/'compact-0000.npz'
        np.savez_compressed(path, **arrays)
        records = []
        for team in [0, 1]:
            records.append(dict(season=season, split='val' if season == sr.VAL_SEASON else 'train',
                                series_id=season+':s', replay_id=season+':r', focal_team=team,
                                player_ids=json.dumps([f'p{i}' for i in ([0,1,2,3,4,5] if team == 0 else [3,4,5,0,1,2])]),
                                roster_id=f'roster:{team}', opponent_roster_id=f'roster:{1-team}',
                                region='EU', fps=10., state_decoding='per_replay_decoded',
                                state_decoding_details=json.dumps({'failures': []}),
                                start=team*n, stop=(team+1)*n))
        pd.DataFrame(records).to_parquet(path.with_suffix('.parquet'))
    # Unlisted files/directories must not be staged, even within an allowed season.
    hidden = source/'rlcs-2026'
    hidden.mkdir()
    (hidden/'secret.npz').write_bytes(b'not valid input')
    (source/'rlcs-2024'/'unrelated.txt').write_text('not input')
    stage = tmp_path/'staged'
    summary = sr.stage_inputs(source, stage)
    assert summary['files'] == 9
    assert not (stage/'rlcs-2026').exists()
    assert not (stage/'rlcs-2024'/'unrelated.txt').exists()
    pairs, _ = sr.inventory(stage)
    for pair in pairs:
        full = list(sr.iter_compact(pair[0]['_shard']))
        for meta, (_, whole) in zip(pair, full):
            sliced = sr.read_player_slice(meta)
            for key, values in sliced.items():
                np.testing.assert_array_equal(values, whole[key])
