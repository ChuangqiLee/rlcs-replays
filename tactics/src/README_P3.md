# P3 RLCS tactics pipeline

Python 3.11 research package for RQ1 rotation grammar, RQ3 pressure/cover, and RQ4 roster style. All commands are local filesystem operations; there is no SSH, downloader, or cluster connection in the package.

## Install and local check

The intended environment is NumPy 2, pandas 3, PyArrow 25, SciPy, scikit-learn, torch 2.5.1 and matplotlib. `statsmodels` is optional. The encoder uses ordinary PyTorch tensors; PyG and `pyg-lib` are unnecessary.

```bash
python -m pip install -e '.[test,mixed]'
python -m pytest -q
python -m tests.synthetic --output tests/_synthetic/data
```

`tests/synthetic.py` generates all five seasons, the exact real column names, one replay per parquet row group, JSON player/header columns, manifest series, and Kaggle-path fallback. It includes goals, resets, mapped overtime, odd-player and failed index rows, and missing positions. Its numeric state codes are **synthetic only**.

`tests/test_pipeline.py` runs all stages, multiprocessing extraction, real parquet round trips, dashboard contract checks, and PNG generation. It skips explicitly if PyArrow is missing. Numerical tests independently cover geometry, identity, strict score timing, hysteresis, touch timing, invariance, encoder gradients, train-only scaling, semi-Markov simulation, series dependence, multiplicity and output contracts.

Local verification in this workspace used Python 3.11 with cached NumPy 2.4.6/pandas 3.0.6 and CPU torch 2.14.0. PyArrow and torch 2.5.1 were unavailable offline, so **the parquet integration and target CUDA environment have not been executed here**. Run the complete test suite in the target environment before interpreting results. `pytest` reports the actual pass/skip count; a skipped integration test is not a successful parquet check.

## Small local fixture run

Run from the directory containing `tactics_code/`:

```bash
python -m tactics_code.audit --data-root tests/_synthetic/data \
  --state-map tests/_synthetic/data/state-map.synthetic.json --output tests/_synthetic/out
python -m tactics_code.extract --data-root tests/_synthetic/data \
  --state-map tests/_synthetic/data/state-map.synthetic.json \
  --output tests/_synthetic/out --workers 2 --max-replays 8
python -m tactics_code.tokens --input tests/_synthetic/out/compact \
  --output tests/_synthetic/out --device cpu --epochs 1 --hidden 8 \
  --window 4 --k 2 --nulls 9 --bootstrap 19
python -m tactics_code.pressure --input tests/_synthetic/out/compact \
  --output tests/_synthetic/out --bootstrap 19
python -m tactics_code.style --input tests/_synthetic/out/compact \
  --output tests/_synthetic/out --min-series 2 --min-events 1 \
  --permutations 19 --bootstrap 19
python -m tactics_code.viz --output tests/_synthetic/out
```

Tiny fixtures test execution and intentionally may fail scientific support/stability gates. Their p-values and figures are not study findings.

## Measurement audit and parser semantics

Default data root: `~/workspace/rlcs-replays/data`.

`audit` scans every index and manifest entry. Native frame scanning streams parquet row groups; without a cap it scans all indexed successful modes. `--max-replays N` limits the frame audit to the same complete-series 3v3 sample used by extraction, while index counts remain complete. Missing staged frame shards and scan scope are reported. Outputs are `results/audit.json` (dashboard envelope with detailed audit under `details`) and `results/audit.md`.

The audit separates the supplied reconciliation, **49,259 − 49,165 = 94 odd-player-count games**, from observed index counts. It reports status/player-count tables, duplicates, manifest conflicts, clock/state/boost/demolition ranges, state code and transition counts, goal-field shapes and timeline coverage, per-team goal agreement with header player totals, stable IDs, and grouping sources. The 134 failures and 26 deleted downloads are not subtracted from parsed-game totals.

Audit and extraction default to `./state_map_rlcs.json` (falling back to the repository copy when run elsewhere). The map records the supplied empirical decoding from rlcs-2024 replay 0 at 30 fps: 73 is kickoff countdown, 78 is live play, and 96 is goal/post-goal. It carries `explicit_state_map` provenance for measurement gates. Override it with `--state-map PATH`; explicit `--live-states` and the exploratory `--allow-heuristic-live` remain available. The state-map keys are:

| Key | Meaning |
|---|---|
| `live_states` | Audited codes admitting live play, including OT when appropriate |
| `kickoff_states`, `goal_replay_states` | Codes always excluded |
| `regulation_states`, `overtime_states` | Codes giving known OT false/true; otherwise OT is unknown |
| `goal_detection` | `frame_state_transitions` enables live → goal/post-goal goal detection when timed metadata is unavailable |
| `overtime_detection` | `frame_state_transitions` derives OT from the zero-clock live → kickoff transition, because live codes are shared by regulation and OT |
| `demolition_absent_values` | Optional audited no-demolition sentinels; indicator duration still needs validation |
| `goals_key`, `goal_time_key`, `goal_time_unit`, `goal_team_key` | Optional alternate goal layout; time unit is `frame` or `time` in the native current-time domain |

Timed metadata decoding accepts `goals: [{"frame": ..., "team": 0/1}]` or `{"time": ..., "team": 0/1}` and checks available header totals. When this timeline is unavailable, the default map derives goals from 78 → 96 transitions with `frame_state_transitions` provenance. The immediately preceding ball y must satisfy `|y| > 5000`: positive y credits team 0 (blue), negative y credits team 1 (orange). Otherwise the scorer is ambiguous, and scores after that goal remain unknown. The audit compares derived per-team goal counts with summed player `Goals` in `replay_meta` and reports agreement. Header totals alone never locate goals. Only goals **strictly before** a frame affect its score.

The default map marks regulation until a 78 → 73 transition at zero seconds remaining without a goal. Subsequent live frames are overtime, including its count-up clock, until the next goal ends golden-goal play. Zero-second live regulation remains distinct from OT; OT is not inferred from a negative timer. Unknown context stays NaN internally and becomes JSON `null`.

The exploratory heuristic accepts positive, decreasing clocks with the hit latch set; it may produce no windows for coarse/integer clocks. It does not validate parser states or support confirmatory interpretation. The default RLCS map handles integer clocks directly through states. Review the reported transitions and goal agreement when applying it to other data; do not copy the synthetic mapping onto real data. Demolition duration semantics remain unverified.

## Compact data and bounded I/O

`extract` includes `status=ok`, six-player, verified 3+3 rosters, irrespective of occasional missing positions. Players are reordered to focal three followed by opponent three. Orange perspective rotates positions and linear velocities by 180° in the horizontal plane, so each focal team attacks +y. Each replay supplies two perspectives.

Per season, `compact-*.npz` holds concatenated numeric arrays and the matching `.parquet` supplies offsets and identity/context metadata. Defaults pack 250 replays per shard. `data.iter_compact(path)` reads one shard at a time. Arrays include ball `[T,6]`, players `[T,6,8]` (position, velocity, raw boost, decoded demolition), flags `[T,6,4]`, roles `[T,3]`, uncertainty, candidate touches, native clock/frame, remaining time, score difference, OT, live mask and segment IDs. Raw state/hit/demolition values remain available. NPZ loads never enable pickle.

Native 30 Hz candidate contacts require proximity, a nearby distance minimum and ball-velocity impulse, exclude arena-surface/ambiguous candidates, and deduplicate. The hit field is treated as a possible kickoff latch, not a contact pulse. Contacts are assigned only to later retained samples and excluded from vocabulary inputs. Roles are distance-to-ball ranks, with default 100-unit / 0.3-second hysteresis and uncertainty for absent cars/near ties; these are proxies, not tactical labels.

`--workers` parallelizes shard tasks; `--shard-replays` bounds worker memory. `--max-replays` is a reproducible **per-season cap**, selecting complete known series where they fit; unknown series remain identified as such and are excluded from grouped inference. Sampling can undershoot the cap. Existing compact output is refused to prevent mixing configurations; use a fresh directory. Large stages are restartable by reusing persisted compact artifacts, not by assuming partially written extraction is complete.

## Analysis protocol

Training is 2021–22/2022–23/2024, validation is 2025, and test is 2026. Complete series, both perspectives and all their windows share a split. Unknown/conflicting grouping is not replaced with a per-game pseudo-series. Roster IDs are hashes of three stable platform/player IDs; color team numbers and display names are never organization IDs. Stage paths are descriptors, not verified elimination-pressure labels.

- **RQ1:** Non-overlapping 4/6/8-second windows at deterministic prospective anchors. Within-team permutation-invariant geometry/motion summaries feed a small masked GRU with trained temporal/future heads. It excludes score, clock, identities, boost, touch and outcomes. The handcrafted control summarizes the same inputs. Scalers, model and centers fit training data; K selection uses validation coverage, two-seed assignment stability and silhouette **within each representation**. This is the requested small encoder, not a completed seven-node graph-model study. Reservoirs bound development fitting (12,000 training/4,000 validation windows by default); every eligible inference window is retained.
- **Grammar:** Run-length sequences reset at replay/team/live-segment/gap boundaries. A training-fitted first-order semi-Markov null samples state-specific dwell times and preserves each sequence's length/reset boundaries; it preserves fitted transition/dwell distributions in expectation, not exact finite-sample counts. Held-out higher-order predictive gain is compared with null sequences, aggregating and bootstrapping by complete series. Candidate motifs come from training data. Vocabulary instability suppresses the primary confirmatory p-value rather than selecting a significant K.
- **RQ3:** Planar own-goal-to-ball corridor coverage, third-man depth and spacing, aggregated to team–series–context rows. Primary contrast is `[late−earlier, trailing by one]−[late−earlier, leading by one]`, with late ≤60 seconds and earlier 60–180. OT, unknown scores and zero-second play are excluded from this regulation contrast and retained descriptively. Crossed roster/series mixed effects are attempted when available/estimable; cluster-robust OLS and whole-series bootstrap provide the fallback. Current geometry, resources and available season/region/roster context enter adjustment. Missing historical opponent strength is disclosed.
- **RQ4:** Training-reference context weights, common ball-zone/score/clock/region support, equal-series fingerprints, and globally disjoint series halves. Compare within-roster with different-roster distances; permute entire second-half roster fingerprints within regional/common-support strata. Default roster eligibility is 20 series across three events, plus independent support in each half. Player profiles retain individual role/cover information. Season token-mixture and within-token geometry drift are descriptive; composition/patch causality is not claimed.

`results/confirmatory.json` applies Holm across the three predeclared RQ1/RQ3/RQ4 tests separately by evaluation split. Missing tests retain family slots; conflicting records cannot be cherry-picked. `results/exploratory.json` pools learned/control motif tests and secondary pressure tests into one BH family across available evaluation splits; within-vocabulary q-values are diagnostics. Insufficient support yields explicit missing estimates and prune reasons, not zero effects. Heuristic state decoding suppresses confirmatory p-values; RQ1/RQ4 also require a stable vocabulary.

By default, tokens never transform 2026 and pressure/style evaluate `--split val`. Opening 2026 requires `tokens --evaluate-test` and `pressure/style/viz --split test`. Freeze seeds, K/window/fps, state decoding, model selection and interpretation before doing so; use a fresh output root for confirmation. Tokens refuse existing model/window artifacts, preventing accidental configuration mixing. No human interpretation or contact/rank annotation is fabricated by this software.

All stages accept `--seed`, `--k`, `--window`, `--fps`, `--run`, and `--output`. Use `tokens --k-sweep 6 8 12 16` for shared-embedding K selection; `--k` alone fixes K. Re-extract for fps/rank sensitivities. Supported native-30-Hz subsamples are 5/10/15/30 Hz. Run robustness configurations in separate output roots, then compare substantive effects; seeds/configurations are not independent observations.

## Cluster deployment and jobs

Copy `tactics_code/` contents to `$HOME/workspace/rlcs-replays/tactics/src/`, the three `slurm/*.sh` files to `tactics/slurm/`, and `state_map_rlcs.json` to `tactics/state_map_rlcs.json`. Jobs also support `src/tactics_code/` if copying the directory intact. They source the existing `slurm/env.sh`; they do not replace it or install packages on the cluster.

```bash
cd "$HOME/workspace/rlcs-replays/tactics"
mkdir -p runs results figures status logs
sbatch slurm/p3_small.sh
sbatch slurm/p3_full.sh
```

Both request `amperenodes`, one A100 and 16 CPUs. Small selects up to about 300 replays per season; full stages all frame shards for the audit. All index/manifest metadata and selected **whole frame shards** are copied to `$TMPDIR` first. Raw Kaggle replay bytes are not copied: a compact path ledger preserves series evidence. Disk capacity is checked. Audit and extraction use `tactics/state_map_rlcs.json` by default. Set `STATE_MAP` to override it, or `ALLOW_HEURISTIC_LIVE=1` for exploratory extraction; an explicit `STATE_MAP` takes precedence.

Override `SEED`, `FPS`, `WINDOW`, `K`, `K_SWEEP`, `WORKERS`, `EPOCHS`, `BOOTSTRAP`, `NULLS` and the small-run `MAX_REPLAYS` through environment variables. Explicit `K` fixes K; otherwise `K_SWEEP` defaults to `6 8 12 16`. `EVALUATE_TEST=1` explicitly opens 2026. Full jobs retain 2,000 bootstrap replicates and 999 grammar null replicates by default; reduced counts are smoke tests only. Jobs acquire a shared output lock and archive preceding analytic artifacts/results before replacing current dashboard results. Concurrent manual CLI runs need separate output roots. No job has been submitted by this task.

## Dashboard and artifacts

Outputs are rooted at `--output` (cluster jobs use `tactics/`):

```text
runs/<run>-<stage>/metrics.jsonl   # append-only, increasing per-split steps
runs/<run>-<stage>/meta.json      # config, timestamps, status
results/*.json                   # method/task/split/is_baseline/finite metrics
results/audit.md
status/ideas.json                 # merged candidates; explicit prune reasons
logs/*.log                       # offset-aware timestamps
artifacts/tokens/                # one checkpoint, codebook metadata, window parquet, medoids
artifacts/pressure/              # context observations and curves
artifacts/style/                 # roster/player/season fingerprints and drift
figures/                        # token_medoids, transition_graph, pressure_curves, fingerprint_heatmap.png
```

Result details carry structured evidence without changing the dashboard-required envelope. JSON writes are atomic, NaN/Infinity become null, metrics maps contain only finite numbers, and existing ideas are merged. No empty example status files overwrite unrelated dashboard state. Jobs archive compact shards and analytic artifacts under `artifacts/<run>/`; there are no per-replay checkpoints. Figures label missing support instead of inventing curves or fingerprints.
