"""Reproduce local acceptance and a synthetic timing scenario, writing locally.

The previous retrieval JSON is used ONLY for input size and measured extraction
timing. It supplies no habit estimates. Run from the task/repository root.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import time
import unittest

import numpy as np
import pandas as pd
import scipy
import statsmodels


def write_implementation(root, report, h):
    """All numerical validation claims are rendered from the saved report."""
    tests, icc = report['tests'], report['icc']
    runtime, synthetic = report['runtime_scenario'], report['synthetic']
    doc = f'''# RQ4 habit stability implementation

The implementation asks which interpretable habits are stable and how much
remains after a teammate change. Outputs describe associations in the observed
players, seasons, and rosters. There is no identity-classification endpoint.

## Delivered files and frozen specification

- `docs/RQ4_habits_prereg.md`: definitions, estimands, missingness, population
  minima, bootstrap, multiplicity, and variance-model fallback. Written before
  code; its original hash is stored in `docs/RQ4_habits_prereg.sha256`.
- `src/tactics_code/habit_stability.py`: compact extraction, aggregation,
  consecutive-season inference, and crossed REML decomposition.
- `src/tests/test_habit_stability.py`: executable unittest acceptance suite.
- `src/tests/validate_habit_stability.py`: rerunnable tests, synthetic inference,
  ICC fixture, runtime scenario, and this generated implementation report.
- `slurm/rq4_habits.sh`: CPU job wrapper; syntax checked locally, not submitted.
- `results/rq4_habits_validation.json`, `results/rq4_habits_synthetic.json`,
  `results/rq4_habits_synthetic_cells.parquet`, and
  `results/rq4_habits_icc_fixture.npz`: validation evidence only.
- `logs/habit_tests.log`, `logs/validation.log`, and `logs/slurm_syntax.log`:
  local verification logs.

The original preregistration hash still matches. Validation hash:
`{report['prereg_sha256']}`. Source: `results/rq4_habits_validation.json`.

## Input contract and output contract

The module reuses the reference package's `screen.metadata_inventory`,
`screen.read_slice`, `style_retrieval.check_rows`, `data.parsed_json`, and
`data.roster_key`. Existing `extract.py`, `style.py`, and `style_retrieval.py`
provide field semantics. It does not reuse retrieval accuracy or learned
representations. It validates stable IDs, roster membership, opposing
perspectives, split labels, array layout, and offsets before feature payloads.
Only explicit development-season paths are inspected. Forbidden paths, including
symlinks into held-out paths, fail closed. There is no held-out override.

Only own-team slots contribute player rows. All derived masks and arrays are new
allocations; compact views and arrays created from immutable byte buffers are
never modified. The sample-exposure definition matches uniform compact sampling;
it does not fill gaps. Unknown demolition status is retained and counted.

Production output-directory contents:

- `player_replays.parquet`: stable player/replay/season/roster IDs, every habit,
  each habit's observed seconds, and unknown demolition counts. Unavailable
  habit values remain missing.
- `player_season_roster.parquet`: equal-replay habit means and usable distinct
  replay counts, without discarding low-count cells from the audit table.
- `roster_history.json`: exact observed teammate sets from all validated input
  metadata, including unusable and unselected replay features.
- `rq4_habits.json`: per-transition estimates, player counts, eligibility by
  season, mixed-roster exclusions, intervals and valid-draw counts, fixed-family
  p/q values, ratio-denominator status, crossed-model diagnostics, input hashes,
  source code/specification hashes, missingness, and stage timings.

The record unit is player-replay, aggregated to player-season-roster. Season
means weight roster cells by each habit's usable replay count; they are not an
equal-roster mean. Overall stability retains mixed-roster seasons; retention
requires a single observed roster in each season. Teammate groups are defined
from exact membership, with the focal player removed, and never from team names.
Habit eligibility is assessed separately in both seasons. Only consecutive
development-season pairs are compared.

Spearman estimates rank stability; ICC estimates absolute agreement in the
original habit units. Resampling selects complete paired player means. Retention
resamples players separately within changed and unchanged groups. The ratio's
interval is suppressed when the unchanged-group correlation is nonpositive or
its interval reaches zero; its raw point value is retained where defined.
It is not labeled a percentage of habit preserved. Overall rho uses player-label
permutations; the difference uses an approximate centered bootstrap test.
Benjamini-Hochberg families include every frozen habit, separately for each
transition and endpoint, with unavailable tests counted conservatively.

Crossed MixedLM uses a single global group, separate player and roster variance
components, and season fixed contrasts. Its cell-mean residual is not frame-level
noise. Support and covariance-design rank are checked before fitting. Optimizers
follow the frozen order and log warnings. If the separated model is unavailable,
the player-only fallback is explicitly labeled as roster-unseparated and never
substituted for the primary decomposition. Boundary estimates remain flagged.

## Local run commands

The snapshot is a read-only dependency, not an output destination. From this task
folder, rerun the complete local acceptance report with:

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$HOME/rlcs-codex/data/repo/src${{PYTHONPATH:+:$PYTHONPATH}}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
"$HOME/rlcs-codex/venv/bin/python" -B src/tests/validate_habit_stability.py \\
  --reference-results "$HOME/rlcs-codex/data/repo/results/rq4_retrieval.json" \\
  > logs/validation.log 2>&1
```

The habit CLI can run directly from this overlay with the same environment, once
an allowed compact exists on this Mac:

```bash
"$HOME/rlcs-codex/venv/bin/python" -B src/tactics_code/habit_stability.py \\
  --compact /absolute/local/path/to/compact \\
  --output-dir "$PWD/results/rq4_habits"
```

For an extraction-only smoke, append `--max-replays` with a positive replay
limit. Smoke mode skips all inference and does not relax the fixed gates. The
full CLI intentionally exposes no minimum-count, feature-selection, test-season,
or replicate-count override. The pure analysis functions accept smaller replicate
counts only for tests. A namespace overlay does not override the snapshot's
regular package, so use direct script execution locally. After integrating the
files into a repository checkout, `python -B -m tactics_code.habit_stability`
is the corresponding module command.

The Slurm wrapper is supplied for later use in an integrated checkout. It expects
the existing `slurm/env.sh`; that file is absent from this local snapshot and has
not been invented. It sources the environment with nounset temporarily disabled,
preserves existing PYTHONPATH, requests the named CPU partition, writes logs,
and guards optional empty arrays using the Bash-compatible expansion required
by the task. It runs the tests before analysis. Optional environment settings
are `RQ4_COMPACT`, `RQ4_OUTPUT_DIR`, and `RQ4_MAX_REPLAYS`.
Create `logs/` before any later submission so scheduler log paths exist.
No scheduler or remote-host command was executed here.

## Measured acceptance and timing

{tests['run']} tests passed, with {tests['failures']} failures and
{tests['errors']} errors, in {tests['seconds']:.3f} seconds. The known synthetic
ICC was {icc['expected']:.6f}; the recovered ICC was {icc['recovered']:.6f}, an
absolute difference of {icc['absolute_error']:.6f}. The saved fixture contains
{icc['targets']} targets and {icc['occasions']} occasions. These values are
computed in `results/rq4_habits_validation.json` from
`results/rq4_habits_icc_fixture.npz`, not empirical replay estimates.

Tests cover exact features and boundary conditions, read-only inputs, slot
equivariance, missing exposure, identity and roster validation, duplicate rows,
metadata offsets, held-out guards, season-specific eligibility, unambiguous
roster changes, paired player resampling, constant margins, denominator failure,
fixed BH families, crossed variance fitting and fallback, and full-versus-slice
reader agreement on a synthetic compact containing an unreadable held-out
sentinel. Shell syntax and empty-array execution passed. The installed Mac Bash
was used; the requested older Linux Bash version was not available for execution.

The complete synthetic inference benchmark used {synthetic['players']} players,
{synthetic['rosters']} rosters, and {synthetic['cells']} cells, with
{synthetic['bootstrap']} bootstrap and {synthetic['permutations']} permutation
replicates, and took {synthetic['inference_seconds']:.3f} seconds on this Mac.
Source: `results/rq4_habits_validation.json`; synthetic results and cell values
are saved alongside it. This does not validate empirical stability.

The full previous retrieval run recorded {runtime['reference_replays']} replays,
{runtime['prior_extraction_seconds']:.3f} seconds of feature extraction, and
{runtime['prior_inventory_seconds']:.3f} seconds of inventory. Source:
`{runtime['reference']}` (only input dimensions and timings used).
Combining those historical times with the synthetic inference benchmark gives
{runtime['baseline_seconds']:.3f} seconds. Applying the explicit planning
multiplier of {runtime['planning_multiplier']:.1f} gives a **conditional runtime
estimate of {runtime['planning_minutes']:.1f} minutes**. The arithmetic and source
hash are saved in `results/rq4_habits_validation.json`.

This is a planning scenario, not a full habit-run benchmark: hardware, I/O,
feature work, model dimensions, and optimizer behavior differ. A larger or
poorly separated crossed model can take much longer. The Slurm time and memory
requests are conservative scheduling ceilings chosen in the wrapper, not
measurements. No staging-time estimate or network transfer is included.

## Caveats and source provenance

No compact replay shards exist in the supplied local snapshot. Consequently no
empirical habit estimates, roster-retention conclusions, or empirical variance
shares were produced. Synthetic output filenames and metadata explicitly say
synthetic. The historical retrieval result is used only for runtime planning.
Its classifier measurements are not evidence for the rewritten question.

Conditional exposure can leave some habits or transitions unavailable. Roster
exclusions narrow the retention population; player-cluster intervals do not
account for all shared-match or shared-roster dependence. Rank stability and
absolute agreement describe different aspects of persistence. Model variance
shares depend on the selected cells, season adjustment, and observed roster
overlap. The player-only fallback does not separate player and roster variation.

The snapshot sources and their hashes are recorded in the validation JSON. All
deliverables are inside this task folder; the reference snapshot was not edited.
No figures or LaTeX were produced, so figure styling and LaTeX compilation do not
apply. No external service or remote host was contacted.
'''
    (root/'docs/RQ4_habits_implementation.md').write_text(doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-results', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    logs, results = root/'logs', root/'results'
    logs.mkdir(exist_ok=True)
    results.mkdir(exist_ok=True)
    test_path = root/'src/tests/test_habit_stability.py'
    spec = importlib.util.spec_from_file_location('test_habit_stability', test_path)
    test = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test)
    h = test.h
    prereg = root/'docs/RQ4_habits_prereg.md'
    digest = hashlib.sha256(prereg.read_bytes()).hexdigest()
    lock = (root/'docs/RQ4_habits_prereg.sha256').read_text().split()[0]
    if digest != lock:
        raise ValueError('Preregistration changed after its pre-code freeze')
    with (logs/'habit_tests.log').open('w') as log, contextlib.redirect_stdout(log):
        start = time.perf_counter()
        suite = unittest.defaultTestLoader.loadTestsFromModule(test)
        outcome = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        test_seconds = time.perf_counter()-start
    if not outcome.wasSuccessful():
        raise RuntimeError('Acceptance tests failed; inspect logs/habit_tests.log')
    shell = subprocess.run(['/bin/bash', '-n', str(root/'slurm/rq4_habits.sh')], capture_output=True, text=True)
    (logs/'slurm_syntax.log').write_text(shell.stdout+shell.stderr+f'exit_code={shell.returncode}\n')
    shell.check_returncode()
    # Confirm the required guard also executes with the Mac's older Bash.
    guard = subprocess.run(['/bin/bash', '-uc', 'A=(); set -- ${A[@]+"${A[@]}"}; test "$#" -eq 0'],
                           capture_output=True, text=True)
    guard.check_returncode()
    cells, history = test.synthetic_cells()
    start = time.perf_counter()
    synthetic = h.analyze(cells, history)
    inference_seconds = time.perf_counter()-start
    rng = np.random.default_rng(1982)
    target_variance, error_variance = 4., 1.
    measurements = rng.normal(0, np.sqrt(target_variance), (50000, 1))+rng.normal(0, np.sqrt(error_variance), (50000, 2))
    expected = target_variance/(target_variance+error_variance)
    estimated = float(h.icc21(measurements))
    np.savez_compressed(results/'rq4_habits_icc_fixture.npz', measurements=measurements,
                        target_variance=target_variance, error_variance=error_variance)
    cells.to_parquet(results/'rq4_habits_synthetic_cells.parquet', index=False)
    synthetic.update(data_kind='synthetic_only_not_empirical', seed=102,
                     cells_source='results/rq4_habits_synthetic_cells.parquet',
                     bootstrap=h.BOOTSTRAP, permutations=h.PERMUTATIONS, prereg_sha256=digest)
    (results/'rq4_habits_synthetic.json').write_text(json.dumps(h.clean_json(synthetic), indent=2, allow_nan=False)+'\n')
    reference = json.loads(args.reference_results.read_text())
    historical_features = reference['timings_seconds']['features']
    historical_inventory = reference['timings_seconds']['inventory']
    # A transparent planning scenario; no unmeasured I/O or fitted empirical model is implied.
    baseline = historical_features+historical_inventory+inference_seconds
    planning_multiplier = 3.
    source_root = Path(h.metadata_inventory.__code__.co_filename).resolve().parents[2]
    source_paths = [source_root/'docs/paper_framing.md'] + [source_root/'src/tactics_code'/name
        for name in ('data.py', 'extract.py', 'style.py', 'style_retrieval.py', 'screen.py')]
    report = dict(data_kind='synthetic_validation_and_conditional_runtime_scenario',
                  source_contracts=[dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in source_paths],
                  implementation_sha256=hashlib.sha256(test.MODULE.read_bytes()).hexdigest(),
                  tests=dict(run=outcome.testsRun, failures=len(outcome.failures), errors=len(outcome.errors),
                             seconds=test_seconds, log='logs/habit_tests.log'),
                  shell_syntax_exit=shell.returncode, empty_array_guard_exit=guard.returncode,
                  prereg_sha256=digest, prereg_hash_matches_precode_lock=digest == lock,
                  icc=dict(expected=expected, recovered=estimated, absolute_error=abs(estimated-expected),
                           fixture='results/rq4_habits_icc_fixture.npz', targets=len(measurements),
                           occasions=measurements.shape[1]),
                  synthetic=dict(cells=len(cells), players=cells.identity_id.nunique(), rosters=cells.roster_id.nunique(),
                                 inference_seconds=inference_seconds, bootstrap=h.BOOTSTRAP, permutations=h.PERMUTATIONS),
                  runtime_scenario=dict(reference=str(args.reference_results),
                      reference_sha256=hashlib.sha256(args.reference_results.read_bytes()).hexdigest(),
                      reference_replays=reference['processed_replays'],
                      prior_extraction_seconds=historical_features, prior_inventory_seconds=historical_inventory,
                      synthetic_inference_seconds=inference_seconds, baseline_seconds=baseline,
                      planning_multiplier=planning_multiplier, planning_minutes=baseline*planning_multiplier/60,
                      limitation='Historical extraction uses a different feature module and machine; synthetic model dimensions are not observed habit eligibility. Crossed REML can be much slower on larger or ill-conditioned designs. This is a conditional planning scenario, not a full-run benchmark.'),
                  environment=dict(platform=platform.platform(), python=platform.python_version(),
                                   numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                                   statsmodels=statsmodels.__version__),
                  real_compact_available=False, empirical_habit_estimates_produced=False, test_opened=False)
    (results/'rq4_habits_validation.json').write_text(json.dumps(h.clean_json(report), indent=2, allow_nan=False)+'\n')
    write_implementation(root, report, h)
    print(json.dumps(h.clean_json(report), indent=2))


if __name__ == '__main__':
    main()
