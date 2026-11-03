"""Bounded orchestration. No training, inventory or tensor import on --list-jobs."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import time
import traceback

from .configs import CONFIGS, N_JOBS, configuration, jobs

ROOT = Path(__file__).resolve().parents[2]


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def provenance():
    sources = sorted((ROOT/'src'/'ai_experiments').glob('*.py'))
    sources += sorted((ROOT/'src'/'pilot_encoder').glob('*.py'))
    sources += [ROOT/'paper'/'AI_PLAN.md', ROOT/'slurm'/'env.sh']
    sources += sorted((ROOT/'slurm').glob('ai_*.sh'))
    sources += [ROOT/'src'/'tactics_code'/name for name in
                ('style_retrieval.py', 'screen.py', 'data.py')]
    return dict(git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)),
                source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sources if p.is_file()})


def _expired(signum, frame):
    raise TimeoutError('Preregistered whole-job operational cap exhausted')


def reference_check(report, dataset, reference):
    """Historical 15.39% is an anchor only when exact source/population match."""
    if reference is None or not reference.is_file():
        return dict(matched=False, reason='Historical reference unavailable; use recomputed paired baseline')
    ref = json.loads(reference.read_text())
    def inputs(rows):
        return sorted((Path(x['path']).parent.name, Path(x['path']).name,
                       x['metadata_sha256'], x['bytes']) for x in rows)
    population = report['population']
    baseline = report.get('primary', {}).get('methods', {}).get('handcrafted', {}).get('metrics', {})
    checks = dict(input_files=inputs(ref.get('input_files', [])) == inputs(dataset.report['input_files']),
                  replays=sorted(ref.get('replay_ids', [])) == dataset.report['replay_ids'],
                  games=ref.get('player_games') == len(dataset.games),
                  ids=ref.get('eligible_ids') == population.get('eligible_ids'),
                  gallery=ref.get('n_gallery') == population.get('n_gallery'),
                  queries=ref.get('primary', {}).get('queries_evaluated') ==
                          report.get('primary', {}).get('queries_evaluated'))
    for metric in ('top1', 'top5', 'mrr'):
        a = ref.get('primary', {}).get('metrics', {}).get(metric, {}).get('estimate')
        b = baseline.get(metric, {}).get('estimate')
        checks[metric] = a is not None and b is not None and abs(a-b)<1e-12
    return dict(matched=all(checks.values()), checks=checks,
                reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                historical_top1=.15392254220456802,
                interpretation='Separate cohort if any check fails; never subtract a historical constant for paired CI')


def run_one(data, cfg, out, device, *, remaining=None):
    import numpy as np
    from .baselines import fit_summary
    from .evaluation import evaluate_methods
    from .training import fit, embed_games
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if remaining is not None:
        cfg = dict(cfg, train_budget_seconds=min(cfg['train_budget_seconds'], remaining-300))
        if cfg['train_budget_seconds'] <= 0:
            raise TimeoutError('Insufficient time after preprocessing to reserve inference')
    features = sorted(c for c in data.games if c.startswith('f_'))
    raw = data.games[features].to_numpy()
    methods = {'handcrafted': dict(values=raw, metric='euclidean', standardize=True),
               'matched_handcrafted': dict(values=data.matched_handcrafted, metric='euclidean', standardize=True),
               'common_summary': dict(values=data.summaries, metric='euclidean', standardize=True)}
    if data.agent_summaries is not None:
        methods['agent_summary'] = dict(values=data.agent_summaries, metric='euclidean', standardize=True)
    training = {}
    if cfg.get('summaries_only'):
        sources = [('handcrafted', raw), ('common_summary', data.summaries)]
        if data.agent_summaries is not None:
            sources.append(('agent_summary', data.agent_summaries))
        for source, values in sources:
            for kind in ('linear', 'mlp'):
                name = f'{source}_{kind}'
                z, training[name] = fit_summary(values, data.games,
                    dict(cfg, train_budget_seconds=cfg['train_budget_seconds']/(2*len(sources)+1)), out/name, device, kind)
                methods[name] = dict(values=z, metric='cosine')
        frozen_cfg = dict(cfg, frozen=True, diagnostic_steps=0)
        model, training['frozen_random'] = fit(data, frozen_cfg, out/'random', device)
        methods['frozen_random'] = dict(values=embed_games(model, data, device, config=frozen_cfg), metric='cosine')
    elif cfg.get('pilot'):
        # Reuse original pilot sampler/objective/architecture, including V4 extras.
        from pilot_encoder.run import fixed_config
        from pilot_encoder.evaluation import embed_games as pilot_embed
        variant = cfg['backbone'].replace('pilot_', '')
        if variant in ('v1', 'v2'):
            from pilot_encoder.training import train_model
        else:
            from pilot_encoder.training_adapted import train_model
            from pilot_encoder.run_adapted import fixed_config
        pilot_cfg = fixed_config(variant, synthetic=cfg['tiny'])
        pilot_cfg.update(seed=cfg['seed'], epochs=cfg['epochs'],
                         train_budget_seconds=cfg['train_budget_seconds'])
        # Pilot checkpoint policy uses TMPDIR; then copy final artifact to results.
        work = Path(os.environ.get('TMPDIR', '/tmp'))/f'ai-pilot-{os.getpid()}-{cfg["name"]}'
        adapted = replace(data, x=data.x if variant == 'v3' else data.pooled_x)
        model, training['learned'] = train_model(adapted.x, adapted.masks, adapted.window_games,
                                               adapted.games, pilot_cfg, work, device)
        frame, columns, timing = pilot_embed(model, adapted, device)
        methods['learned'] = dict(values=frame[columns].to_numpy(), metric='cosine')
        training['learned']['inference'] = timing
        shutil.copytree(work, out/'pilot_checkpoint', dirs_exist_ok=True)
    else:
        model, training['learned'] = fit(data, cfg, out/'checkpoint', device)
        inference_start = time.monotonic()
        z = embed_games(model, data, device, config=cfg)
        training['learned']['embedding_seconds'] = time.monotonic()-inference_start
        methods['learned'] = dict(values=z, metric='cosine')
    if 'learned' in methods:
        methods['learned_centered'] = dict(values=methods['learned']['values'], metric='cosine', center=True)
        methods['learned_euclidean'] = dict(values=methods['learned']['values'], metric='euclidean', standardize=True)
        methods['fusion'] = dict(components=['handcrafted', 'learned'], weights=[.5, .5])
    atomic_json(out/'training.json', training)
    np.savez_compressed(out/'embeddings.npz', **{name: spec['values'] for name, spec in methods.items() if 'values' in spec})
    evaluation = evaluate_methods(data.games, data.metadata, methods, bootstrap=cfg['bootstrap'], seed=42)
    atomic_json(out/'evaluation.json', evaluation)
    return dict(config=cfg, training=training, evaluation=evaluation, seconds=time.monotonic()-started)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--list-jobs', action='store_true')
    mode.add_argument('--smoke', action='store_true')
    mode.add_argument('--diagnose', action='store_true')
    mode.add_argument('--job-index', type=int)
    parser.add_argument('--compact', type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    args = parser.parse_args(argv)
    if args.list_jobs:
        print(json.dumps(jobs(), indent=2))
        return
    if args.job_index is not None and not 0 <= args.job_index < N_JOBS:
        parser.error(f'--job-index must be in 0..{N_JOBS-1}')
    if not args.smoke and (not os.environ.get('SLURM_JOB_ID') or args.device != 'cuda'):
        parser.error('Real-data runs require SLURM and CUDA')
    if args.out_dir is None or args.scratch is None:
        parser.error('--out-dir and --scratch are required')
    if args.smoke and args.compact is not None:
        parser.error('Smoke constructs its own synthetic fixture; --compact is forbidden')
    if not args.smoke and args.compact is None:
        parser.error('--compact must explicitly name the approved compact cohort')
    out, scratch = args.out_dir.resolve(), args.scratch.resolve()
    if not args.smoke and out != ROOT/'results'/'ai'/os.environ['SLURM_JOB_ID']:
        parser.error('Production outputs must be results/ai/<SLURM_JOB_ID>/')
    allowed_scratch = Path(os.environ.get('TMPDIR', '/tmp')).resolve()
    if allowed_scratch == Path('/') or allowed_scratch not in scratch.parents:
        parser.error('--scratch must be below TMPDIR (or /tmp locally)')
    if (out/'report.json').exists():
        parser.error('Refusing to overwrite an existing report')
    out.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    start_epoch = float(os.environ.get('AI_START_EPOCH', time.time()))
    budget = 1000 if args.smoke else 1200 if args.diagnose else 3000
    report = dict(status='running', synthetic=args.smoke, test_opened=False,
                  created_utc=datetime.now(timezone.utc).isoformat(), **provenance(),
                  total_budget_seconds=budget, historical_results_not_replaced=True)
    try:
        remaining = budget-(time.time()-start_epoch)
        if remaining <= 0:
            raise TimeoutError('Environment setup exhausted operational budget')
        signal.signal(signal.SIGALRM, _expired)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        import torch
        from tactics_code.screen import guard_path
        from .dataset import build_dataset
        from .training import train_only_gate
        torch.set_num_threads(1 if args.smoke else min(8, int(os.environ.get('SLURM_CPUS_PER_TASK', '8'))))
        if args.device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA required; no silent CPU fallback')
        report['hardware'] = dict(python=platform.python_version(), torch=str(torch.__version__),
                                  cuda=torch.version.cuda, device=torch.cuda.get_device_name(0) if args.device == 'cuda' else 'cpu')
        cfg = configuration(args.job_index if args.job_index is not None else 15, smoke=args.smoke)
        if args.smoke:
            from pilot_encoder.tests.fixture import make_fixture
            source = make_fixture(scratch/'synthetic', frames=120)
        else:
            source = guard_path(args.compact).resolve()
            extraction = json.loads(guard_path(source/'extraction.json').read_text())
            if extraction.get('synthetic_only') or extraction.get('options', {}).get('synthetic'):
                raise ValueError('Real experiment cannot accept a synthetic source')
        data = build_dataset(source, scratch/'cache', cfg, train_only=args.diagnose)
        report['dataset'] = data.report
        report['compact_source'] = str(source)
        data.games.to_csv(out/'game_manifest.csv', index=False)
        atomic_json(out/'metadata.json', data.metadata)
        shutil.copyfile(data.report['selection_file'], out/'selection.json')
        atomic_json(out/'report.json', report)
        if args.diagnose:
            report['gates'] = {}
            for config_index in [1, 2, 3, 4, 5, 6, 7, 13, 14]:
                gate_cfg = configuration(config_index*3)
                gate_cfg['diagnostic_steps'] = 100
                result = train_only_gate(data, gate_cfg, args.device,
                                         deadline=time.monotonic()+max(0, budget-(time.time()-start_epoch)-10))
                report['gates'][gate_cfg['name']] = result
                atomic_json(out/'report.json', report)
            if not all(g['passed'] for g in report['gates'].values()):
                raise RuntimeError('Training-only overfit gate failed; experiment array must not run')
        elif args.smoke:
            report['runs'] = {}
            for index in range(len(CONFIGS)):
                tiny = configuration(index*3, smoke=True)
                # Two-step smoke checks every trainer; the real diagnostic gate
                # subsequently enforces the preregistered memorization threshold.
                tiny['diagnostic_steps'] = 0
                result = run_one(data, tiny, out/tiny['name'], args.device)
                report['runs'][tiny['name']] = dict(seconds=result['seconds'], status=result['evaluation']['status'])
                atomic_json(out/'report.json', report)
            # Separately execute the non-disabled diagnostic branch, synthetic only.
            report['diagnostic'] = train_only_gate(data, dict(configuration(15, True), diagnostic_steps=30), args.device)
            if not report['diagnostic']['passed']:
                raise RuntimeError('Synthetic diagnostic gate failed')
        else:
            result = run_one(data, cfg, out/'experiment', args.device,
                             remaining=budget-(time.time()-start_epoch))
            report['experiment'] = dict(config=result['config'], training=result['training'], seconds=result['seconds'])
            report['historical_comparison'] = reference_check(result['evaluation'], data, ROOT/'results'/'rq4_retrieval.json')
        report['status'] = 'complete'
    except Exception as exc:
        report.update(status='failed', error=dict(type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc()))
        if hasattr(exc, 'report'):
            report['training_failure'] = exc.report
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report['whole_job_seconds'] = time.time()-start_epoch
        atomic_json(out/'report.json', report)
        print(json.dumps(dict(output=str(out), status=report['status'], synthetic=args.smoke)), flush=True)
