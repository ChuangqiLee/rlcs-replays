"""Bounded temporary storage for the unchanged possession design matrix.

No analysis settings live here.  Row order, TRAIN vocabulary, float32 input
encoding and float64 standardization follow the existing implementations.
"""
from __future__ import annotations

import numpy as np

from . import pushup_dr as dr


def possession_feature_matrix(df, train_mask):
    """Build the original possession matrix once, without stacked one-hot lists."""
    # Import at call time so the original module can optionally use this helper.
    from .pushup_possession import TOUCH_LEVELS

    regions = sorted(set(df.loc[train_mask, 'region']))
    identities = sorted(set(df.loc[train_mask, 'last_man_id']))
    numeric = dr.NUMERIC_FEATURES + ['last_man_y_own', 'last_man_behind_ball']
    names = (list(numeric) + [f'region={region}' for region in regions]
             + [f'last_man_id={identity}' for identity in identities]
             + [f'last_touch_team={level}' for level in TOUCH_LEVELS]
             + ['ball_vy_attack', 'ball_in_opp_half'])
    x = np.empty((len(df), len(names)), dtype=np.float32)
    column = 0
    for name in numeric:
        values = df[name].to_numpy(dtype=np.float32)
        if not np.isfinite(values).all():
            raise ValueError('Nonfinite baseline controls; no silent covariate imputation')
        x[:, column] = values
        column += 1
    for name, levels in (('region', regions), ('last_man_id', identities)):
        for level in levels:
            x[:, column] = (df[name] == level).to_numpy(dtype=np.float32)
            column += 1
    if not df['last_touch_team'].isin(TOUCH_LEVELS).all():
        raise ValueError('Unknown last_touch_team level')
    for level in TOUCH_LEVELS:
        x[:, column] = (df['last_touch_team'] == level).to_numpy(dtype=np.float32)
        column += 1
    for name in ('ball_vy_attack', 'ball_in_opp_half'):
        values = df[name].to_numpy(dtype=np.float32)
        if not np.isfinite(values).all():
            raise ValueError('Nonfinite possession covariates')
        x[:, column] = values
        column += 1
    return x, names, regions


def _column_blocks(width, block_columns):
    if block_columns < 2:
        raise ValueError('block_columns must be at least two')
    lo = 0
    while lo < width:
        hi = min(lo + block_columns, width)
        # A lone final column would change NumPy's reduction from a strided
        # axis to a contiguous axis.  Fold it into the preceding block.
        if width - hi == 1:
            hi = width
        yield lo, hi
        lo = hi


def training_moments(x, train_mask, block_columns=32):
    """Original TRAIN mean/std, with only a small column block in temporaries.

    This retains row order and dtype=float reductions.  Because NumPy/BLAS
    implementations can vary, medium equivalence checks must still compare
    these arrays within the predeclared numerical tolerance.
    """
    center = np.empty(x.shape[1], dtype=float)
    spread = np.empty(x.shape[1], dtype=float)
    for lo, hi in _column_blocks(x.shape[1], block_columns):
        train = x[:, lo:hi][train_mask]
        center[lo:hi] = train.mean(axis=0, dtype=float)
        spread[lo:hi] = train.std(axis=0, dtype=float)
    return center, spread


def standardized_rows(x, mask, center, spread, block_columns=32):
    """Select rows before float64 standardization, preserving element operations."""
    selected = np.flatnonzero(mask)
    result = np.empty((len(selected), x.shape[1]), dtype=float)
    for lo, hi in _column_blocks(x.shape[1], block_columns):
        result[:, lo:hi] = x[:, lo:hi][selected]
    result -= center
    result /= spread
    return result
