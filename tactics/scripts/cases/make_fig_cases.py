#!/usr/bin/env python3
"""Render small, self-contained case parquet files; no native replay access."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import string
import sys
import textwrap

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def escape_tex(text):
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
               '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(mapping.get(c, c) for c in text)


def check_latex(text):
    """Structural check only; no local LaTeX installation is required."""
    stack, envs = [], []
    for line in text.splitlines():
        line = re.split(r'(?<!\\)%', line)[0]
        for match in re.finditer(r'\\(begin|end)\{([^}]+)\}|(?<!\\)[{}]', line):
            if match.group(1):
                kind, name = match.group(1, 2)
                if kind == 'begin': envs.append(name)
                elif not envs or envs.pop() != name: raise ValueError('Unbalanced LaTeX environment')
            elif match.group() == '{': stack.append('{')
            elif not stack: raise ValueError('Unbalanced LaTeX brace')
            else: stack.pop()
    if stack or envs: raise ValueError('Unclosed LaTeX brace/environment')


def validate(table, meta, path):
    import numpy as np
    required = {'case_id', 'figure_group', 'panel_index', 'outcome', 'replay_id', 'series_id',
                'season', 'split', 'is_synthetic', 'focal_team', 'entity', 'player_slot', 'team',
                'time', 'relative_time', 'frame', 'x', 'y', 'live', 'segment', 'is_last_man',
                'is_anchor_last_man', 'game_clock', 'score_team0', 'score_team1'}
    if not required <= set(table): raise ValueError(f'Missing columns: {sorted(required - set(table))}')
    if table.empty: raise ValueError('No cases')
    if digest(path) != meta['parquet_sha256']: raise ValueError('Parquet hash does not match cases_meta.json')
    if not (table.season.eq(meta['season']) & table.split.eq('val')).all() or meta['season'] != 'rlcs-2025':
        raise ValueError('Only validation season cases are permitted')
    if not table.is_synthetic.eq(meta['is_synthetic']).all(): raise ValueError('Mixed/incorrect synthetic provenance')
    if table[['case_id', 'frame', 'entity']].duplicated().any(): raise ValueError('Duplicate entity-frame rows')
    if not table.groupby(['case_id', 'frame']).size().eq(7).all(): raise ValueError('Expected ball and all players')
    if not np.isfinite(table[['x', 'y']].to_numpy()).all(): raise ValueError('Missing coordinates')
    for group in ('main', 'appendix'):
        expected = meta['constants'][group + '_count']
        cases = table[table.figure_group.eq(group)]
        if cases.case_id.nunique() != expected: raise ValueError(f'Incorrect {group} case count')
        if sorted(cases.panel_index.unique()) != list(range(expected)): raise ValueError('Invalid panel ordering')
    for c in meta['selected']:
        sample = table[table.case_id.eq(c['case_id'])]
        if not (sample.replay_id.eq(c['replay_id']) & sample.series_id.eq(c['series_id'])).all():
            raise ValueError('Case provenance disagrees with metadata')
        anchors = sample[np.isclose(sample.relative_time, 0)]
        if len(anchors) != 7: raise ValueError('Missing crossing frame')


def caption(table, meta, group):
    const = meta['constants']
    cases = sorted((c for c in meta['selected'] if c['figure_group'] == group), key=lambda c: c['panel_index'])
    season = meta['season'].removeprefix('rlcs-')
    provenance = ('SYNTHETIC SELF-TEST DATA ONLY; these panels contain no real replay observations.'
                  if meta['is_synthetic'] else f'Real {season} val data from the project native per-frame replay files.')
    method = ('the empirical upper tercile of eligible validation-frame depth'
              if meta['threshold']['method'] == 'empirical' else 'the attacking third of field length')
    lines = [provenance,
             f"{len(cases)} illustrative cases: live regulation clock above zero and at most {const['late_seconds']:g} s, "
             f"with the focal team trailing by one goal at the crossing into {method}.",
             f"The threshold is {meta['threshold']['value']:.2f} uu from the own goal line. "
             f"Shown windows span {const['half_window_seconds']:g} s before and after the crossing at {const['fps']:g} Hz.",
             f"Scored/conceded denotes the first goal in the next {const['outcome_seconds']:g} s; "
             'neither denotes no goal during the known follow-up, allowing a certified game end. '
             'The labels use the focal-team perspective. Outcome strata are sampled by design; these panels do not show outcome frequencies.',
             'The focal team attacks upward. Team colors follow the native team assignment; the ball is dark. '
             'The defender who is the geometric last man at the crossing is highlighted in gold throughout the window. '
             'Markers show the crossing frame, and trajectories fade from earlier to later replay time. '
             'Nonlive frames, native segment interruptions, gaps, and large position jumps are not joined. '
             'The geometric last man can change identity during the window.']
    for c in cases:
        symbol = string.ascii_lowercase[c['panel_index']]
        own, opp = ((c['score_team0'], c['score_team1']) if c['focal_team'] == 0 else
                    (c['score_team1'], c['score_team0']))
        lines.append(f"({symbol}) {c['outcome']}; replay_id={c['replay_id']}; series_id={c['series_id']}; "
                     f"frame={c['anchor_frame']}; clock={c['clock_at_crossing']:.1f} s; focal score={own}-{opp}.")
    return lines


def render(table, meta, group, out, style):
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import to_rgba
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle, Circle
    const = meta['constants']
    ncols = 3 if group == 'main' else 4
    nrows = int(np.ceil(meta['constants'][group + '_count'] / ncols))
    width = style.DOUBLE_COL_IN
    height = width * (nrows / ncols) * 1.35 + 1.0
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), squeeze=False)
    fig.subplots_adjust(left=.055, right=.985, top=.88, bottom=.075, wspace=.29, hspace=.40)
    half_x, half_y = const['field_half_width'], const['field_half_length']
    cases = sorted((c for c in meta['selected'] if c['figure_group'] == group), key=lambda c: c['panel_index'])
    threshold_y = meta['threshold']['value'] - half_y
    for ax, c in zip(axes.flat, cases):
        sample = table[table.case_id.eq(c['case_id'])]
        ax.add_patch(Rectangle((-half_x, -half_y), 2 * half_x, 2 * half_y,
                               facecolor='#FAFAF8', edgecolor=style.PALETTE['tied'], lw=.6, zorder=0))
        ax.axhline(0, color=style.PALETTE['tied'], lw=.4, alpha=.35)
        ax.add_patch(Circle((0, 0), half_x / 5, fill=False, edgecolor=style.PALETTE['tied'], lw=.4, alpha=.35))
        ax.axhline(threshold_y, color=style.PALETTE['accent'], ls='--', lw=.7, alpha=.8)
        # Simple goal-mouth marks; the playing field retains its specified extents.
        for yy in (-half_y, half_y):
            ax.plot([-half_x / 4, half_x / 4], [yy, yy], color=style.PALETTE['ball'], lw=1.8)
        for _, entity in sample.groupby('entity', sort=True):
            e = entity.sort_values('time')
            xy, times = e[['x', 'y']].to_numpy(), e.relative_time.to_numpy()
            live, segment = e.live.to_numpy(bool), e.segment.to_numpy()
            valid = (live[:-1] & live[1:] & (segment[:-1] == segment[1:]) & (segment[:-1] >= 0) &
                     (np.diff(times) > 0) & (np.diff(times) <= 1.6 / const['fps']))
            player = int(e.player_slot.iloc[0])
            # Same player-jump screen as the project; avoid drawing teleports.
            if player >= 0:
                valid &= np.linalg.norm(np.diff(xy, axis=0), axis=1) <= 500.
            is_last = bool(e.is_anchor_last_man.iloc[0])
            color = style.PALETTE['ball'] if player < 0 else (
                style.PALETTE['accent'] if is_last else style.PALETTE[f'team{int(e.team.iloc[0])}'])
            alpha = .12 + .82 * (times[1:] + const['half_window_seconds']) / (2 * const['half_window_seconds'])
            rgba = np.tile(to_rgba(color), (len(alpha), 1))
            rgba[:, 3] = alpha
            segments = np.stack([xy[:-1], xy[1:]], axis=1)
            ax.add_collection(LineCollection(segments[valid], colors=rgba[valid],
                              linewidths=1.55 if is_last else (.85 if player < 0 else .65),
                              zorder=4 if is_last else (3 if player < 0 else 2)))
            anchor = np.flatnonzero(np.isclose(times, 0))[0]
            ax.scatter(*xy[anchor], s=38 if is_last else (14 if player < 0 else 10),
                       marker='*' if is_last else ('o' if player < 0 else '^'), color=color,
                       edgecolors='white', linewidths=.35, zorder=6)
        ax.set_xlim(-half_x, half_x)
        ax.set_ylim(-half_y, half_y)
        ax.set_aspect('equal')
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values(): spine.set_visible(False)
        own, opp = ((c['score_team0'], c['score_team1']) if c['focal_team'] == 0 else (c['score_team1'], c['score_team0']))
        ax.set_title(f"{c['outcome'].capitalize()}\n{c['clock_at_crossing']:.1f} s  |  focal {own}–{opp}", fontsize=7, pad=5)
        style.panel_label(ax, string.ascii_lowercase[c['panel_index']])
        ax.text(.5, -.035, c['case_id'], transform=ax.transAxes, ha='center', va='top', fontsize=5.8)
    for ax in list(axes.flat)[len(cases):]: ax.set_axis_off()
    if group == 'main':
        note_ax = axes.flat[-1]
        note = (f"Focal team attacks ↑\n\nDashed line: tercile boundary\n"
                f"Star: last man at crossing\n\nTime fades from\n−{const['half_window_seconds']:g} to +{const['half_window_seconds']:g} s\n\n"
                'Outcome strata are sampled.\nPanel frequencies are not rates.\n\nReplay and series IDs\nare listed in the caption.')
        note_ax.text(.02, .86, note, transform=note_ax.transAxes, va='top', fontsize=7, linespacing=1.45)
    title = 'SYNTHETIC SELF-TEST • no real replay observations' if meta['is_synthetic'] else (
        f"Real {meta['season'].removeprefix('rlcs-')} val data • late trailing-by-one crossings")
    fig.suptitle(title, fontsize=9, fontweight='bold', y=.98)
    fig.text(.5, .94, f"{len(cases)} {group} cases  |  first goal within {const['outcome_seconds']:g} s after crossing", ha='center', fontsize=7)
    handles = [Line2D([], [], color=style.PALETTE[key], lw=1.5, label=label) for key, label in
               (('team0', 'Blue team'), ('team1', 'Orange team'), ('ball', 'Ball'), ('accent', 'Last man at crossing'))]
    fig.legend(handles=handles, loc='lower center', ncol=len(handles), bbox_to_anchor=(.5, .005), fontsize=6)
    stem = f'fig_cases_{group}'
    png = out / f'{stem}.png'
    fig.savefig(png, dpi=300, facecolor='white')
    # Portable vector output needs no TeX installation.
    fig.savefig(out / f'{stem}.pdf', facecolor='white')
    plt.close(fig)
    return png


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', required=True, type=Path)
    parser.add_argument('--meta', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    local_repo = HERE.parent.parent / 'data' / 'repo'
    parser.add_argument('--repo', type=Path, default=Path(os.environ.get('RLCS_REPO', str(local_repo if local_repo.exists() else Path.cwd()))))
    args = parser.parse_args()
    args.out, args.repo = args.out.resolve(), args.repo.resolve()
    if args.out == args.repo or args.out.is_relative_to(args.repo): parser.error('--out must be outside the snapshot')
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ['MPLCONFIGDIR'] = str(args.out / '.mplconfig')
    import matplotlib
    matplotlib.use('Agg')
    import pandas as pd
    sys.path.insert(0, str(args.repo / 'paper' / 'figures'))
    import nature_style as style
    style.apply()
    meta_path = args.meta or args.cases.with_name('cases_meta.json')
    meta = json.loads(meta_path.read_text())
    table = pd.read_parquet(args.cases)
    validate(table, meta, args.cases)
    outputs = []
    for group in ('main', 'appendix'):
        png = render(table, meta, group, args.out, style)
        lines = caption(table, meta, group)
        txt = args.out / f'fig_cases_{group}_caption.txt'
        txt.write_text('\n\n'.join(lines) + '\n')
        source = f"% src: {args.cases.resolve()}; {meta_path.resolve()}"
        latex = '\\caption{ ' + source + '\n' + '\n'.join(escape_tex(s) + ' ' + source for s in lines) + '\n} ' + source + '\n'
        check_latex(latex)
        tex = args.out / f'fig_cases_{group}_caption.tex'
        tex.write_text(latex)
        outputs.append(dict(group=group, png=str(png), png_sha256=digest(png),
                            panel_count=int(table[table.figure_group.eq(group)].case_id.nunique()),
                            caption=str(txt), latex=str(tex), latex_structure='balanced braces/environments'))
    report = dict(status='rendered', is_synthetic=meta['is_synthetic'], source_parquet=str(args.cases.resolve()),
                  source_sha256=digest(args.cases), source_metadata=str(meta_path.resolve()),
                  style_source=str(args.repo / 'paper' / 'figures' / 'nature_style.py'),
                  style_sha256=digest(args.repo / 'paper' / 'figures' / 'nature_style.py'),
                  width_inches=style.DOUBLE_COL_IN, outputs=outputs,
                  caveat='LaTeX structure checked only; no TeX compilation. Visual inspection is a separate step.')
    (args.out / 'render_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
