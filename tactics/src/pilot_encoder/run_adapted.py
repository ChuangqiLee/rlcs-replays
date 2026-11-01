"""Isolated V3/V4 orchestration; V1/V2 continue using the unchanged run.py."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import time
import traceback

from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS, VAL_SEASON, guard_path
from tactics_code.style_retrieval import DEFAULT_COMPACT, MIN_GAMES

from .dataset import build_dataset, stage_compact

ROOT = Path(__file__).resolve().parents[2]


def fixed_config(variant, synthetic=False):
    """Fixed addendum settings; the original V1/V2 configuration is untouched."""
    from .run import fixed_config as original_config
    if variant not in ('v3', 'v4'):
        raise ValueError('Adapted runner accepts only v3/v4')
    config = original_config(variant, synthetic)
    config.update(
        variant_family=['v1', 'v2', 'v3', 'v4'], report_all_variants=True,
        multiplicity='per-variant unadjusted claims; no selection',
        v3=dict(width=16 if synthetic else 128, spatial_layers=1 if synthetic else 2,
                heads=2 if synthetic else 4, feedforward=32 if synthetic else 256,
                btm_layers=1 if synthetic else 4, state_size=4 if synthetic else 8,
                dt_rank=2 if synthetic else 8, convolution_kernel=4,
                dropout=0.1, rms_epsilon=1e-5, ghost_probability=0.15,
                input_shape=[60, 7, 16], roles=['query', 'teammate', 'opponent', 'ball'],
                dt_initial=0.1, production_parameters=1121408),
        v4=dict(width=16 if synthetic else 128, layers=1 if synthetic else 4,
                recurrent_heads=2 if synthetic else 4, feedforward=32 if synthetic else 256,
                patch_frames=6, convolution_kernel=4, rms_epsilon=1e-5,
                denominator_floor=1e-6, dropout=0.1, patch_mask_probability=0.5,
                contiguous_mask_patches=2, input_shape=[60, 38],
                extra_identities_per_base_identity=1, windows_per_extra_identity=2,
                production_parameters=708992),
    )
    return config


def provenance():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    sources = list((ROOT/'src'/'pilot_encoder').rglob('*.py'))
    sources += [ROOT/'paper'/'PILOT_ENCODER.md', ROOT/'slurm'/'pilot_encoder.sh',
                ROOT/'src'/'tactics_code'/'style_retrieval.py', ROOT/'src'/'tactics_code'/'screen.py',
                ROOT/'src'/'tactics_code'/'data.py']
    return {'git_commit': git('rev-parse', 'HEAD'),
            'git_dirty': bool(git('status', '--porcelain')),
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(sources) if p.exists()}}


def _atomic_report(out, report):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(out.suffix+'.tmp')
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    temporary.replace(out)


def _timeout(signum, frame):
    raise TimeoutError('Preregistered 9000-second whole-job operational budget exhausted')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=['v3', 'v4'], required=True)
    parser.add_argument('--compact', type=Path, default=DEFAULT_COMPACT)
    parser.add_argument('--source-compact', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--checkpoint-dir', type=Path)
    parser.add_argument('--reference', type=Path, default=ROOT/'results'/'rq4_retrieval.json')
    parser.add_argument('--stage-to', type=Path)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    parser.add_argument('--synthetic-smoke', action='store_true', help='Only accepts marked synthetic fixtures; never production PASS')
    args = parser.parse_args(argv)
    if not args.synthetic_smoke and not os.environ.get('SLURM_JOB_ID'):
        parser.error('Production/staging must run inside SLURM; local tests require --synthetic-smoke')
    compact = guard_path(args.compact).resolve()
    extraction = json.loads(guard_path(compact/'extraction.json').read_text())
    if args.synthetic_smoke:
        if extraction.get('synthetic_only') is not True or extraction.get('options', {}).get('synthetic') is not True:
            parser.error('--synthetic-smoke requires an explicitly marked synthetic compact fixture')
        if args.device != 'cpu':
            parser.error('Synthetic smoke is CPU only')
    elif args.device != 'cuda':
        parser.error('Production requires --device cuda')
    elif extraction.get('synthetic_only') or extraction.get('options', {}).get('synthetic'):
        parser.error('Synthetic compact requires --synthetic-smoke; cannot produce empirical results')
    if args.source_compact:
        guard_path(args.source_compact)
    config = fixed_config(args.variant, args.synthetic_smoke)
    started = time.perf_counter()
    job_start = float(os.environ.get('PILOT_START_EPOCH', time.time()))
    elapsed_before = max(0., time.time()-job_start)
    remaining = config['total_budget_seconds']-elapsed_before
    out = args.out or ROOT/'results'/f'pilot_encoder_{args.variant}.json'
    if args.synthetic_smoke and (ROOT/'results') in out.resolve().parents:
        parser.error('Synthetic results must be written to scratch, never production results/')
    checkpoint_dir = args.checkpoint_dir or ROOT/'artifacts'/'pilot_encoder'/args.variant
    report = dict(schema_version=1, analysis='PILOT learned PLAYER identity retrieval',
                  status='running', mode='synthetic_smoke' if args.synthetic_smoke else 'full',
                  synthetic=args.synthetic_smoke, config=config, **provenance(),
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  compact_source=str(args.source_compact or compact), staged_compact=str(compact),
                  min_games_per_season=MIN_GAMES, train_seasons=list(TRAIN_SEASONS), val_season=VAL_SEASON,
                  test_opened=False, allowed_seasons=list(ALLOWED_SEASONS),
                  methods='paper/PILOT_ENCODER.md; RQ4 infer reused unchanged; cosine embedding distances',
                  pass_criterion='Primary Top-1 ci95[0] > 0.177 and same RQ4 population/source',
                  pass_decision=False, timings_seconds={'environment_and_staging': elapsed_before},
                  learned_token_baseline={'status': 'not_evaluated', 'reason':
                      'Frozen artifacts absent locally; original team GRU/codebook uses 2025 model selection. See preregistration.'})
    try:
        if remaining <= 0:
            raise TimeoutError('Whole-job operational time budget already exhausted')
        signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        if args.stage_to:
            report['staging'] = stage_compact(compact, args.stage_to)
            report['status'] = 'staged'
            return
        import torch
        from .training_adapted import train_model
        from .training import checkpoint_destination
        from .evaluation import embed_games, evaluate_embeddings, recompute_handcrafted, compare_reference
        torch.set_num_threads(1 if args.synthetic_smoke else min(16, int(os.environ.get('SLURM_CPUS_PER_TASK', '16'))))
        if not args.synthetic_smoke and not torch.cuda.is_available():
            raise RuntimeError('CUDA is required for production pilot')
        report['hardware'] = dict(platform=platform.platform(), machine=platform.machine(),
                                  python=platform.python_version(), torch=str(torch.__version__),
                                  cuda=torch.version.cuda, torch_threads=torch.get_num_threads(),
                                  device=torch.cuda.get_device_name(0) if args.device == 'cuda' else platform.processor())
        checkpoint_dir = checkpoint_destination(checkpoint_dir)
        if args.variant == 'v3':
            from .dataset_v3 import build_dataset as selected_builder
        else:
            selected_builder = build_dataset
        data = selected_builder(compact, checkpoint_dir/'cache', config)
        report.update({k: v for k, v in data.report.items() if k != 'timings_seconds'})
        report['timings_seconds'].update(data.report['timings_seconds'])
        time_left = config['total_budget_seconds']-(time.time()-job_start)
        effective = min(config['train_budget_seconds'], time_left-1800.)
        if effective <= 0:
            raise TimeoutError('Insufficient budget remaining after extraction to reserve inference')
        training_config = dict(config, train_budget_seconds=effective)
        model, training = train_model(data.x, data.masks, data.window_games, data.games,
                                      training_config, checkpoint_dir, args.device)
        report['training'] = training
        report['timings_seconds']['training'] = training['fit_seconds']
        _atomic_report(out, report)
        frame, columns, timing = embed_games(model, data, args.device)
        report['timings_seconds'].update(timing)
        inference_start = time.perf_counter()
        learned = evaluate_embeddings(frame, columns, data.metadata,
                                      config['permutations'], config['bootstrap'], config['seed'])
        report.update(learned)
        report['timings_seconds']['learned_inference'] = time.perf_counter()-inference_start
        baseline_start = time.perf_counter()
        handcrafted = recompute_handcrafted(data, config)
        report['handcrafted_same_games'] = handcrafted
        report['timings_seconds']['handcrafted_inference'] = time.perf_counter()-baseline_start
        if args.synthetic_smoke:
            report['comparison'] = {'same_protocol_population_and_source': False,
                                    'reason': 'Synthetic fixture; no empirical baseline comparison'}
        elif guard_path(args.reference).exists():
            reference_bytes = guard_path(args.reference).read_bytes()
            report['reference_sha256'] = hashlib.sha256(reference_bytes).hexdigest()
            report['comparison'] = compare_reference(json.loads(reference_bytes), handcrafted, learned, data.report)
        else:
            report['comparison'] = {'same_protocol_population_and_source': False,
                                    'reason': 'Baseline JSON missing; cannot certify matching RQ4 population/source'}
        lower = learned.get('primary', {}).get('metrics', {}).get('top1', {}).get('ci95', [None])[0]
        report['pass_decision'] = bool(not args.synthetic_smoke and lower is not None and lower > .177 and
                                       report['comparison']['same_protocol_population_and_source'])
        report['n_queries'] = learned.get('primary', {}).get('queries_evaluated', 0)
    except Exception as exc:
        report.update(status='failed', pass_decision=False,
                      error={'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report['timings_seconds']['pipeline_total'] = time.perf_counter()-started
        report['timings_seconds']['whole_job_elapsed'] = time.time()-job_start
        _atomic_report(out, report)
        print(json.dumps({'output': str(out), 'status': report['status'], 'synthetic': args.synthetic_smoke,
                          'n_gallery': report.get('n_gallery'), 'n_queries': report.get('n_queries'),
                          'primary': report.get('primary'), 'pass_decision': report['pass_decision'],
                          'timings_seconds': report['timings_seconds']}), flush=True)


if __name__ == "__main__":
    main()
