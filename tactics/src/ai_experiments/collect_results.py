"""Collect fingerprint dev/final evaluations into tidy tables for the paper.

Scans results/ai_dev/<job>/<preset>/{training,evaluation}.json and
results/ai_dev/<job>/evaluation.json (checkpoint evaluations) and writes a
CSV with one row per (job, preset, method, metric) and a Markdown summary.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def rows_from_evaluation(job, preset, evaluation, training=None):
    out = []
    if evaluation.get('status') != 'fit':
        return out
    pop = evaluation['population']
    for analysis in ('primary', 'team_context_control'):
        block = evaluation.get(analysis, {})
        for method, res in block.get('methods', {}).items():
            row_preset = preset
            if preset == 'checkpoint' and ':' in method:
                row_preset = method.split(':', 1)[1]
                method = method.split(':', 1)[0].replace('centered', 'learned_centered')
            for metric, val in res['metrics'].items():
                diff = res['paired_difference_vs_baseline'][metric]
                gallery = pop.get('n_gallery')
                out.append(dict(job=job, preset=row_preset, mode=evaluation.get('mode'),
                                population=('medium' if gallery == 112 else 'full') if evaluation.get('mode') == 'final' else 'dev',
                                eval_season=evaluation.get('evaluation_season_original', evaluation.get('evaluation_season')),
                                analysis=analysis, method=method, metric=metric,
                                estimate=val['estimate'], lo=val['ci95'][0], hi=val['ci95'][1],
                                diff=diff['estimate'], diff_lo=diff['ci95'][0], diff_hi=diff['ci95'][1],
                                queries=block.get('queries_evaluated'), n_series=block.get('n_series'),
                                gallery=pop.get('n_gallery'), bootstrap=block.get('bootstrap'),
                                seed=(training or {}).get('config', {}).get('seed'),
                                steps=(training or {}).get('config', {}).get('steps'),
                                windows_per_game=(training or {}).get('config', {}).get('windows_per_game'),
                                fit_seconds=(training or {}).get('fit_seconds'),
                                parameters=(training or {}).get('encoder_parameters')))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('results/ai_dev'))
    parser.add_argument('--out', type=Path, default=Path('results/ai_dev/collected.csv'))
    args = parser.parse_args(argv)
    rows = []
    for job_dir in sorted(args.root.glob('*')):
        if not job_dir.is_dir():
            continue
        direct = job_dir / 'evaluation.json'
        if direct.exists():
            rows += rows_from_evaluation(job_dir.name, 'checkpoint', json.loads(direct.read_text()))
        for preset_dir in sorted(job_dir.glob('*/')):
            ev = preset_dir / 'evaluation.json'
            if ev.exists():
                tr = preset_dir / 'training.json'
                rows += rows_from_evaluation(job_dir.name, preset_dir.name, json.loads(ev.read_text()),
                                             json.loads(tr.read_text()) if tr.exists() else None)
    if not rows:
        print('no results')
        return
    with args.out.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} rows -> {args.out}')
    final = [r for r in rows if r['mode'] == 'final']
    if final:
        final_path = args.out.parent.parent / 'ai_final' / 'collected.csv'
        final_path.parent.mkdir(parents=True, exist_ok=True)
        with final_path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(final[0]))
            writer.writeheader()
            writer.writerows(final)
        print(f'{len(final)} final rows -> {final_path}')
    lines = ['| job | preset | eval | method | top1 [95% CI] | paired Δtop1 vs handcrafted | top5 | mrr |', '|---|---|---|---|---|---|---|---|']
    primary = [r for r in rows if r['analysis'] == 'primary']
    keyed = {}
    for r in primary:
        keyed.setdefault((r['job'], r['preset'], r['eval_season'], r['method']), {})[r['metric']] = r
    for (job, preset, season, method), m in keyed.items():
        t = m['top1']
        lines.append(f"| {job} | {preset} | {season} | {method} | {t['estimate']:.3f} [{t['lo']:.3f},{t['hi']:.3f}] | "
                     f"{t['diff']:+.3f} [{t['diff_lo']:+.3f},{t['diff_hi']:+.3f}] | {m['top5']['estimate']:.3f} | {m['mrr']['estimate']:.3f} |")
    args.out.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
