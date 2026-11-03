"""Frozen finite experiment matrix; no result-dependent selection."""
from copy import deepcopy

SEEDS = (42, 43, 44)
CONFIGS = [
    dict(name='summaries', backbone='transformer', summaries_only=True),
    *[dict(name=f'pilot_v{i}', backbone=f'pilot_v{i}', inputs='agents' if i == 3 else 'pooled',
           objective='window', pooling='mean', pilot=True) for i in range(1, 5)],
    dict(name='game_transformer', backbone='transformer'),
    dict(name='game_gru', backbone='gru'),
    dict(name='game_mamba', backbone='mamba'),
    dict(name='game_mamba_no_mask', backbone='mamba', masking=False),
    dict(name='game_mean', backbone='transformer', pooling='mean'),
    dict(name='window_mean', backbone='transformer', pooling='mean', objective='window'),
    dict(name='game_attention', backbone='transformer', pooling='attention'),
    dict(name='game_pooled', backbone='transformer', inputs='pooled'),
    dict(name='game_slstm', backbone='slstm', inputs='pooled'),
    dict(name='game_patch_transformer', backbone='patch_transformer', inputs='pooled'),
    dict(name='game_slstm_no_mask', backbone='slstm', inputs='pooled', masking=False),
    dict(name='game_slstm_random', backbone='slstm', inputs='pooled', extra_negatives='random'),
    dict(name='game_slstm_cooccurring', backbone='slstm', inputs='pooled', extra_negatives='cooccurring'),
    dict(name='game_exposure32', backbone='transformer', max_windows_per_game=32),
    dict(name='game_pretrain', backbone='transformer', pretrain_steps=100),
]
N_JOBS = len(CONFIGS) * len(SEEDS)


def configuration(index, smoke=False):
    if not 0 <= index < N_JOBS:
        raise ValueError(f'job-index must be in [0,{N_JOBS-1}]')
    cfg = dict(seed=SEEDS[index % len(SEEDS)], selection_seed=42, window_frames=60,
               max_windows_per_game=8, inputs='agents', objective='game', pooling='meanstd',
               masking=True, extra_negatives='none', pretrain_steps=0,
               epochs=5, batch_identities=8, games_per_identity=2, max_steps=10000,
               train_budget_seconds=2400, total_budget_seconds=3000,
               learning_rate=3e-4, weight_decay=1e-4, temperature=.1,
               bootstrap=2000, inference_seed=42, tiny=False)
    cfg.update(deepcopy(CONFIGS[index // len(SEEDS)]))
    if smoke:
        cfg.update(tiny=True, epochs=1, max_steps=2, batch_identities=2,
                   max_windows_per_game=2, bootstrap=20, train_budget_seconds=30)
        if cfg['pretrain_steps']:
            cfg['pretrain_steps'] = 2
    return cfg


def jobs():
    return [dict(index=i, name=configuration(i)['name'], seed=configuration(i)['seed'])
            for i in range(N_JOBS)]
