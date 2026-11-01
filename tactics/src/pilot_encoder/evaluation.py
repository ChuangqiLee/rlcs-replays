"""RQ4 aggregation/inference with learned cosine distances, no fitted whitening."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import torch

from tactics_code.style_retrieval import (check_rows, eligible_players, identity_regions,
                                          context_maps, infer, evaluate_retrieval)
from .dataset import assert_allowed


def _unit(x):
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    if not np.isfinite(x).all() or np.any(norms <= 1e-12):
        raise ValueError('Nonfinite or zero aggregate embedding')
    return x / norms


def embed_games(model, dataset, device, batch_size=64):
    """Average normalized windows once per game, retaining equal game weighting."""
    started = time.perf_counter()
    model.eval()
    sums = np.zeros((len(dataset.games), 128), dtype=np.float64)
    counts = np.zeros(len(dataset.games), dtype=np.int64)
    with torch.inference_mode():
        for start in range(0, len(dataset.x), batch_size):
            stop = min(start+batch_size, len(dataset.x))
            x = torch.as_tensor(np.asarray(dataset.x[start:stop]), device=device)
            masks = torch.as_tensor(np.asarray(dataset.masks[start:stop]), device=device)
            z = model(x, masks).cpu().numpy()
            game_ids = dataset.window_games[start:stop]
            np.add.at(sums, game_ids, z)
            np.add.at(counts, game_ids, 1)
    if np.any(counts == 0):
        raise AssertionError('Every usable game must have at least one embedding')
    frame = dataset.games.copy()
    columns = [f'e_{i:03d}' for i in range(128)]
    frame = pd.concat([frame, pd.DataFrame(sums/counts[:, None], columns=columns)], axis=1)
    return frame, columns, {'embedding': time.perf_counter()-started,
                            'embedding_windows_per_second': len(dataset.x)/(time.perf_counter()-started)}


def evaluate_embeddings(frame, features, metadata, permutations=2000, bootstrap=2000, seed=42):
    assert_allowed(frame)
    if frame.duplicated(['identity_id', 'season', 'replay_id']).any():
        raise ValueError('Duplicate player-game')
    train, val = frame[frame.split == 'train'], frame[frame.split == 'val']
    check_rows(train, 'train')
    check_rows(val, 'val')
    eligible = eligible_players(train, val)
    regions = identity_regions(metadata)
    ids = [p for p in eligible if p in regions]
    report = dict(eligible_before_region=len(eligible), excluded_unknown_train_region=len(eligible)-len(ids),
                  n_gallery=len(ids), eligible_ids=ids)
    if len(ids) < 2:
        return dict(report, status='insufficient_data', reason='Fixed RQ4 gate leaves fewer than two identities')
    # Same equal-game aggregation as RQ4, without featurewise scaling of embeddings.
    gallery = train.groupby('identity_id', sort=True)[features].mean().loc[ids].to_numpy()
    grouped = val[val.identity_id.isin(ids)].groupby(['identity_id', 'series_id'], sort=True)
    q = grouped[features].mean().reset_index()
    query_rosters = grouped.roster_id.agg(lambda values: set(values)).to_list()
    # Small Q x G table: explicit dot reduction avoids platform BLAS floating
    # status warnings and keeps every cosine bounded/checked before inference.
    distances = 1 - np.einsum('ij,kj->ik', _unit(q[features].to_numpy()), _unit(gallery), optimize=False)
    if not np.isfinite(distances).all():
        raise ValueError('Nonfinite cosine distance')
    distances = np.clip(distances, 0., 2.)
    targets = np.array([ids.index(p) for p in q.identity_id])
    rosters, teammates = context_maps(metadata)
    allowed = np.array([[not (rosters[p] & query_rosters[i]) and p not in teammates[identity]
                         for p in ids] for i, identity in enumerate(q.identity_id)])
    args = (q.series_id.to_numpy(), np.array([regions[p] for p in ids]), permutations, bootstrap, seed)
    keys = list(zip(q.identity_id, q.series_id))
    report.update(status='fit', distance='cosine after equal-game means',
                  primary=infer(distances, targets, np.ones_like(allowed), *args),
                  team_context_control=infer(distances, targets, allowed, *args),
                  query_keys_sha256=hashlib.sha256(json.dumps(keys).encode()).hexdigest())
    return report


def recompute_handcrafted(dataset, config):
    frame = dataset.games
    features = sorted(c for c in frame if c.startswith('f_'))
    return evaluate_retrieval(frame[frame.split == 'train'], frame[frame.split == 'val'],
                              features, dataset.metadata, config['permutations'],
                              config['bootstrap'], config['seed'])


def compare_reference(reference, handcrafted, learned, dataset_report):
    """Source + population + recomputed baseline must match for an empirical PASS."""
    def files(items):
        return sorted((str(Path(row['path']).parent.name+'/'+Path(row['path']).name),
                       row['metadata_sha256'], row['bytes']) for row in items)
    checks = {
        'reference_full_fit': reference.get('mode') == 'full' and reference.get('status') == 'fit',
        'input_metadata_and_shard_sizes': files(reference.get('input_files', [])) == files(dataset_report['input_files']),
        'replay_ids': sorted(reference.get('replay_ids', [])) == sorted(dataset_report['replay_ids']),
        'player_games': reference.get('player_games') == dataset_report['player_games'],
        'player_games_by_season': reference.get('player_games_by_season') == dataset_report['player_games_by_season'],
        'eligible_ids': reference.get('eligible_ids') == handcrafted.get('eligible_ids') == learned.get('eligible_ids'),
        'gallery': reference.get('n_gallery') == handcrafted.get('n_gallery') == learned.get('n_gallery'),
    }
    for analysis in ('primary', 'team_context_control'):
        expected = reference.get(analysis, {})
        actual = handcrafted.get(analysis, {})
        encoded = learned.get(analysis, {})
        for key in ('queries_total', 'queries_evaluated', 'n_series', 'excluded_true_identity',
                    'excluded_fewer_than_two_candidates', 'candidate_count', 'null_stratum_sizes'):
            checks[f'{analysis}_{key}'] = expected.get(key) == actual.get(key) == encoded.get(key)
        for metric in ('top1', 'top5', 'mrr'):
            a = expected.get('metrics', {}).get(metric, {}).get('estimate')
            b = actual.get('metrics', {}).get(metric, {}).get('estimate')
            checks[f'handcrafted_{analysis}_{metric}'] = a is not None and b is not None and bool(np.isclose(a, b, rtol=0, atol=1e-12))
    return {'same_protocol_population_and_source': all(checks.values()), 'checks': checks,
            'failed_checks': [name for name, passed in checks.items() if not passed]}
