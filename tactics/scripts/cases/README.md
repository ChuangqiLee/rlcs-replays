These scripts extract and render descriptive replay cases. All work delivered here was performed on this Mac using synthetic native-schema frames. No real replay extraction, remote command, network request, or batch submission was performed.

`extract_cases.py` imports the repository's readers, coordinate rotation, live-state decoder, native goal certification, last-man geometry, availability screen, and follow-up labeling. `make_fig_cases.py` imports `paper/figures/nature_style.py`, calls `apply()`, and uses its palette, double-column width, and panel labels. The repository snapshot is read-only; bytecode writes into it are disabled.

**Run the local acceptance checks**

```bash
~/rlcs-codex/venv/bin/python ~/rlcs-codex/work/cases/extract_cases.py \
  --repo ~/rlcs-codex/data/repo \
  --out ~/rlcs-codex/work/cases/synthetic --self-test

~/rlcs-codex/venv/bin/python ~/rlcs-codex/work/cases/make_fig_cases.py \
  --repo ~/rlcs-codex/data/repo \
  --cases ~/rlcs-codex/work/cases/synthetic/cases.parquet \
  --out ~/rlcs-codex/work/cases/synthetic/figures
```

The optional physical-field definition has its own synthetic check:

```bash
~/rlcs-codex/venv/bin/python ~/rlcs-codex/work/cases/extract_cases.py \
  --repo ~/rlcs-codex/data/repo \
  --out ~/rlcs-codex/work/cases/synthetic_field --self-test --tercile field
```

**Operator command — run only in the operator's existing batch environment**

The following is a submission recipe, not a command executed during this task. Place the delivered Python scripts in `RLCS_CASES_DIR` beforehand, and activate the project's Python environment. The repository and compact paths below follow the snapshot's project layout and recorded extraction artifact. Change the variables if the operator's local paths differ. The output directory is separate from the project code. Scheduler account/partition options depend on the operator's allocation and may need to be added to `sbatch`.

```bash
export RLCS_PROJECT_ROOT='~/workspace/rlcs-replays'
export RLCS_REPO="$RLCS_PROJECT_ROOT/tactics"
export RLCS_CASES_DIR="$RLCS_PROJECT_ROOT/work/cases"
export RLCS_COMPACT="$RLCS_REPO/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact"
export RLCS_NATIVE_DATA="$RLCS_PROJECT_ROOT/data"
export RLCS_PYTHON="$(command -v python)"

mkdir -p "$RLCS_CASES_DIR"
sbatch --job-name=cases-val --cpus-per-task=1 --mem=16G --time=06:00:00 \
  --output="$RLCS_CASES_DIR/cases-%j.log" <<'SBATCH'
#!/usr/bin/env bash
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1
"$RLCS_PYTHON" "$RLCS_CASES_DIR/extract_cases.py" \
  --repo "$RLCS_REPO" \
  --compact "$RLCS_COMPACT" \
  --data-root "$RLCS_NATIVE_DATA" \
  --state-map "$RLCS_REPO/state_map_rlcs.json" \
  --tercile empirical \
  --out "$RLCS_CASES_DIR/real"
"$RLCS_PYTHON" "$RLCS_CASES_DIR/make_fig_cases.py" \
  --repo "$RLCS_REPO" \
  --cases "$RLCS_CASES_DIR/real/cases.parquet" \
  --out "$RLCS_CASES_DIR/real/figures"
SBATCH
```

Resource requests in that recipe are operational starting settings, not measured runtime or memory estimates. Dependencies are Python, NumPy, pandas, PyArrow, Matplotlib, SciPy, scikit-learn, statsmodels, joblib, and threadpoolctl; the latter imports follow the existing project modules. No LaTeX installation is needed. The operator must have the reviewed state map, original native frame shards, and existing validation compact metadata. The snapshot contains code and result artifacts but not those native inputs.

**Selection and measurement**

- Only `rlcs-2025` / `val` is accepted. The replay universe and source series IDs come from `compact/rlcs-2025/compact-*.parquet`. No compact arrays are opened. The project `native_index_for` resolves those IDs exclusively against the matching validation season's native indexes. The script validates season paths and symlinks before index access. Frame row-group replay-ID statistics must be present and unambiguous before the original `iter_frame_replays` loader is used; its read-all fallback is never allowed. Other season directories, global manifests, and raw replay files are not opened.
- The default forward tercile is the empirical upper third of geometric `last_man_y_own` across eligible sampled validation frames. Eligibility is live regulation play with a strictly positive clock at or below the requested late boundary, a focal score difference of minus one, known series membership, verified native goals, and the project's valid-track screen. Pooling gives frames equal weight; series are not equally weighted. The threshold is computed before outcome stratification. This is a descriptive validation threshold, not the training-frozen threshold used by the project's separate depth analysis. `--tercile field` instead uses the attacking third of the physical field.
- A crossing requires the previous sampled depth below the threshold and the current depth at or above it. Both adjacent frames must be eligible and share the same native live segment. Sampling uses `extract_replay`'s native-frame stride; the original timestamps are retained, with no interpolation. Exact timing is therefore limited by the sampled cadence.
- The next-goal outcome follows `build_replay_events` and `event_labels`: the first goal in the requested horizon is scored or conceded from the focal team's view. If both teams score, the first event defines the stratum; all goals in the horizon remain in metadata. Missing intervals or unverified truncated follow-up are unknown and excluded. A certified game end is absorbing. This is replay time, not accumulated live-play time.
- Seeded SHA256 ordering is stable under input reordering. Deterministic matching first reserves a distinct main replay for each outcome stratum, then a scored/conceded/neither round robin fills main and appendix slots. A replay is used only once across both figures. Series may recur. If support is insufficient, the script fails and leaves `candidate_audit.json`; it does not duplicate panels or invent cases.
- Display windows require full temporal support and finite ball/player XY tracks. Nonlive rows remain in the parquet for provenance, but the renderer does not plot them or join across native segment boundaries, temporal gaps, or large player-position jumps. Late/trailing eligibility applies to the crossing, not every display frame. Outcomes can occur after the plotted window ends.
- The focal team attacks positive y. Orange focal perspectives rotate both x and y using the original `extract_replay`; no independent coordinate convention is introduced. The literal last man is the minimum-y focal player, computed by `last_man_arrays`, not proximity-role rank. Gold highlights the defender identified at the crossing, whose identity is fixed for the displayed trajectory. The per-frame geometric last-man flag can identify a different defender later.

The extractor makes a depth-distribution pass, a crossing/outcome pass, and a final selected-window pass. It keeps eligible scalar depths in memory for the exact empirical quantile and re-reads native inputs rather than writing a large compact cache. The raw replay observations are never copied to another host by either script.

**Output schema and sources**

`cases.parquet` is a long table with a row for each entity at each sampled frame. It stores ball and player XY, canonical player slot, player ID, native team, focal-team proximity role, per-frame geometric last-man flag, anchor last-man flag, replay ID, series ID, season/split, game clock, both team scores, focal score difference, native frame/time, relative time, live state, segment, overtime, case/panel assignment, outcome, and synthetic provenance. Opponent proximity roles and the ball's role/team use the documented unknown/not-applicable sentinel. Player team is preserved separately from focal orientation.

`cases_meta.json` stores the selection rule, measured threshold and population size, input paths/hashes, source code hashes, state-map configuration, candidate/selected counts, selected anchors and goal events, caveats, and the parquet hash. `candidate_audit.json` stores the full qualifying-candidate inventory and exclusion counters. Synthetic native fixtures are in `synthetic_inputs/`; self-test results are in `self_test_report.json`.

Each rendered group has PNG and PDF figures plus plain-text and LaTeX captions. Captions list full replay and series IDs for every panel. Real-data outputs explicitly say “Real 2025 val data”; synthetic outputs explicitly say “SYNTHETIC SELF-TEST DATA ONLY.” Counts, clocks, scores, depth thresholds, identifiers, and numeric display settings are read from the parquet/metadata. Numeric settings originate in the task's specification; they are not data estimates. Every generated LaTeX caption line carries `% src:` links to the source files. LaTeX is checked only for balanced braces and environments, without compilation. `render_report.json` records the style source, hashes, figure width, panel counts, and structural checks.

Source references in the read-only snapshot:

- `docs/paper_framing.md`: binding descriptive wording and validation scope.
- `src/tactics_code/data.py`: native schema, frame loading, state-map loading, and roster parsing.
- `src/tactics_code/extract.py`: sampling, live/score context, role ranks, and focal-team rotation.
- `src/tactics_code/pressure.py`: geometric last-man calculation.
- `src/tactics_code/events.py`: allowed-season native lookup and goal/terminal certification.
- `src/tactics_code/pushup_dr.py`: track availability and competing first-goal follow-up.
- `results/extract.json`: reviewed state-map configuration used by the synthetic fixture, plus the reference compact extraction layout.
- `paper/figures/nature_style.py`: figure typography, palette, widths, and panel lettering.

**Caveats**

The deliverable has been exercised on synthetic inputs only. Real-data coverage, candidate counts, and visual quality remain for the operator to verify after batch extraction. Outcome stratification deliberately determines panel composition; these examples do not estimate outcome rates or support an interpretation beyond descriptive sequences. Goal validation matches the project's native state decoder to header totals, not independent video review. Raw demolition IDs do not establish persistent absence; the project availability screen reduces some stale-track problems. Unknown series membership and missing native row-group statistics stop extraction. The empirical tercile definition is the documented default because “forward tercile” was not otherwise specified.

**Recorded local verification**

The empirical fixture passed 25 checks and the field-tercile fixture passed 25 checks (sources: `synthetic/self_test_report.json`, `synthetic_field/self_test_report.json`). The empirical output contains 17 cases and 19,159 entity-frame rows; its parquet is 74,254 bytes (sources: `synthetic/cases_meta.json` and the file itself). The main/appendix panel counts are 5 and 12, at 7.16 inches width (source: `synthetic/figures/render_report.json`). Both final PNGs were visually inspected. The source hashes, syntax checks, caption checks, and inspection notes are in `acceptance_report.json`.
