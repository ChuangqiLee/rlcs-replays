"""Render the first four descriptive research figures from pipeline artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from .common import Run, add_common_args, finalize_family, read_json


def _empty(ax, message):
    ax.text(.5, .5, message, ha='center', va='center', transform=ax.transAxes, wrap=True)
    ax.set_axis_off()


def _field(ax):
    from matplotlib.patches import Rectangle, Circle
    ax.add_patch(Rectangle((-4096, -5120), 8192, 10240, fill=False, color='#667085'))
    ax.plot([-4096, 4096], [0, 0], color='#98a2b3', lw=.7)
    ax.add_patch(Circle((0, 0), 915, fill=False, color='#98a2b3', lw=.7))
    for y in (-5120, 5120):
        ax.plot([-893, 893], [y, y], color='#101828', lw=3)
    ax.set(xlim=(-4400, 4400), ylim=(-5550, 5550), aspect='equal', xticks=[], yticks=[])
    ax.set_xlabel('Focal team attacks ↑', fontsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)


def medoid_figure(path, target, plt):
    if not path.exists():
        fig, ax = plt.subplots(figsize=(7, 4))
        _empty(ax, 'Token medoids unavailable: run the vocabulary stage with eligible training windows.')
    else:
        with np.load(path, allow_pickle=False) as archive:
            ball, players, tokens = archive['ball'], archive['players'], archive['token']
        n = len(tokens)
        columns = min(4, max(1, n))
        fig, axs = plt.subplots(int(np.ceil(n / columns)), columns, figsize=(columns * 3, int(np.ceil(n / columns)) * 3.5), squeeze=False)
        for ax in axs.flat:
            ax.set_axis_off()
        for i, ax in enumerate(axs.flat):
            if i >= n:
                continue
            ax.set_axis_on()
            _field(ax)
            for car in range(6):
                color = '#1570ef' if car < 3 else '#f79009'
                ax.plot(players[i, :, car, 0], players[i, :, car, 1], color=color, lw=1, alpha=.7)
                ax.scatter(players[i, -1, car, 0], players[i, -1, car, 1], c=color, s=18, marker='^' if car < 3 else 's')
            ax.plot(ball[i, :, 0], ball[i, :, 1], color='#101828', lw=1.2)
            ax.scatter(ball[i, -1, 0], ball[i, -1, 1], c='#101828', s=20)
            ax.set_title(f'Token {int(tokens[i])}', fontsize=11)
        fig.suptitle('Anonymous training medoids · blue focal / orange opponent / black ball', fontsize=11)
    fig.tight_layout()
    fig.savefig(target, dpi=170, bbox_inches='tight')
    plt.close(fig)


def transition_figure(path, target, plt):
    fig, ax = plt.subplots(figsize=(8, 7))
    if not path.exists():
        _empty(ax, 'Transition matrix unavailable: no eligible training token sequences.')
    else:
        matrix = np.load(path, allow_pickle=False)
        n = len(matrix)
        angle = np.linspace(0, 2 * np.pi, n, endpoint=False)
        points = np.column_stack([np.cos(angle), np.sin(angle)])
        for i in range(n):
            # Two strongest outgoing edges per state keep the first atlas readable.
            order = [j for j in np.argsort(matrix[i])[::-1] if j != i][:2]
            for j in order:
                if matrix[i, j] <= 0:
                    continue
                ax.annotate('', xy=points[j] * .91, xytext=points[i] * .91,
                            arrowprops={'arrowstyle': '->', 'color': '#98a2b3',
                                        'lw': .5 + 4 * matrix[i, j], 'alpha': .65,
                                        'connectionstyle': 'arc3,rad=0.1'})
        ax.scatter(points[:, 0], points[:, 1], s=650, c='#d1e9ff', edgecolors='#1570ef', zorder=3)
        for i, point in enumerate(points):
            ax.text(*point, str(i), ha='center', va='center', zorder=4)
        ax.set(xlim=(-1.2, 1.2), ylim=(-1.2, 1.2), aspect='equal')
        ax.set_axis_off()
        ax.set_title('Training token transitions\nTwo strongest non-self edges; width ∝ conditional probability')
    fig.tight_layout()
    fig.savefig(target, dpi=170, bbox_inches='tight')
    plt.close(fig)


def pressure_figure(path, target, plt, split):
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.8))
    data = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    if not data.empty:
        data = data[(data.split == split) & (data.overtime == 0) & ~data.zero_second & data.score_diff.isin([-1, 0, 1])]
    labels = {'uncovered': 'Uncovered live fraction', 'third_depth': 'Third-man depth (game units)', 'spacing': 'Mean pair spacing (game units)'}
    for ax, (measure, label) in zip(axs, labels.items()):
        if data.empty or measure not in data or not np.isfinite(data[measure]).any():
            _empty(ax, 'No eligible known-score regulation data')
            continue
        for score, color in [(-1, '#d92d20'), (0, '#667085'), (1, '#1570ef')]:
            subset = data[data.score_diff == score].sort_values('time_bin')
            ax.plot((subset.time_bin + .5) * 30, subset[measure], marker='o', markersize=3,
                    label={-1: 'Trailing by 1', 0: 'Tied', 1: 'Leading by 1'}[score], color=color)
        ax.axvline(60, color='#98a2b3', linestyle='--', lw=.8)
        ax.set(xlabel='Seconds remaining', ylabel=label)
        ax.invert_xaxis()
    if not data.empty:
        axs[0].legend(fontsize=8)
    fig.suptitle(f'{split}: descriptive series/context averages · adjusted contrast in results/pressure.json', fontsize=10)
    fig.tight_layout()
    fig.savefig(target, dpi=170, bbox_inches='tight')
    plt.close(fig)


def fingerprint_figure(path, target, plt):
    data = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    if 'entity_type' in data:
        data = data.loc[data.entity_type == 'roster'].copy()
    fig, ax = plt.subplots(figsize=(10, 6))
    features = sorted([c for c in data if c.startswith('token_') and pd.api.types.is_numeric_dtype(data[c])],
                      key=lambda name: int(name.removeprefix('token_')))
    if not features or data.empty:
        _empty(ax, 'No eligible context-standardised roster fingerprints.\nIdentity and independent-series support gates are retained.')
    else:
        keys = [k for k in ('entity_id', 'half') if k in data]
        selected = data.head(32)
        matrix = selected[features].to_numpy(float)
        image = ax.imshow(matrix, aspect='auto', cmap='Blues', vmin=0, vmax=max(.01, np.nanmax(matrix)))
        ax.set_xticks(np.arange(len(features)), features, rotation=60, ha='right', fontsize=8)
        labels = [' / '.join(str(row[k])[-16:] for k in keys) for _, row in selected.iterrows()]
        ax.set_yticks(np.arange(len(selected)), labels, fontsize=7)
        ax.set_title('Context-standardised token usage · first 32 supported fingerprints')
        fig.colorbar(image, ax=ax, label='Token fraction')
    fig.tight_layout()
    fig.savefig(target, dpi=170, bbox_inches='tight')
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument('--artifacts', type=Path, help='Default OUTPUT/artifacts')
    parser.add_argument('--split', choices=['val', 'test'], default='val')
    args = parser.parse_args(argv)
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    artifact = args.artifacts or args.output / 'artifacts'
    figure = args.output / 'figures'
    figure.mkdir(parents=True, exist_ok=True)
    with Run(args, 'viz', method='P3 descriptive research figures') as run:
        medoid_figure(artifact / 'tokens' / 'medoids.npz', figure / 'token_medoids.png', plt)
        run.metric(figures=1)
        transition_figure(artifact / 'tokens' / 'transition.npy', figure / 'transition_graph.png', plt)
        run.metric(figures=2)
        pressure_figure(artifact / 'pressure' / 'curves.parquet', figure / 'pressure_curves.png', plt, args.split)
        run.metric(figures=3)
        fingerprint_figure(artifact / 'style' / 'fingerprints.parquet', figure / 'fingerprint_heatmap.png', plt)
        run.metric(figures=4)
        finalize_family(args.output)
        run.result('viz', {'figures': 4}, split=args.split,
                   details={'paths': [str(p.relative_to(args.output)) for p in sorted(figure.glob('*.png'))]},
                   notes='Descriptive figures. Empty panels explicitly show unavailable or insufficient artifacts.')
        run.idea('p3-figures', 'Initial interpretability atlas', 'selected', motivation='Inspectable geometry and uncertainty-aware summaries')


if __name__ == '__main__':
    main()
