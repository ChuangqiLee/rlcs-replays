#!/bin/bash
# Shared implementation. Submit p3_small.sh or p3_full.sh from tactics/.
set -eo pipefail  # no -u: bash 4.2 treats empty arrays as unbound
: "${TMPDIR:?SLURM must provide node-local TMPDIR}"
: "${P3_MODE:?Submit p3_small.sh or p3_full.sh}"
if [[ "$P3_MODE" != small && "$P3_MODE" != full ]]; then
  echo 'P3_MODE must be small or full' >&2
  exit 2
fi
P3_ROOT="$HOME/workspace/rlcs-replays/tactics"
P3_DATA="${DATA_ROOT:-/home/c.li16@students.uu.nl/workspace/rlcs-replays/data}"
P3_RUN="p3-${P3_MODE}-${SLURM_JOB_ID:-local}-s${SEED:-42}-w${WINDOW:-6}-f${FPS:-10}-k${K:-sweep}"
P3_SCRATCH="$TMPDIR/$P3_RUN"
P3_ARTIFACTS="$P3_ROOT/artifacts/$P3_RUN"
mkdir -p "$P3_ROOT"/{runs,results,figures,status,logs}
cd "$P3_ROOT"
# Current dashboard artifacts/results have shared names: serialize the ENTIRE
# pipeline, not individual JSON writes, to prevent mixed models and Holm families.
exec 9> "$P3_ROOT/status/p3-pipeline.lock"
if ! flock -n 9; then
  echo 'Another P3 pipeline owns the current dashboard artifacts; submit after it finishes.' >&2
  exit 75
fi
# A repeated run identifier must not mix old and new derived data.
if [[ -e "$P3_ARTIFACTS" ]]; then
  echo "Run archive already exists: $P3_ARTIFACTS; use a fresh SLURM job/run." >&2
  exit 2
fi
mkdir -p "$P3_SCRATCH" "$P3_ARTIFACTS"
# Accept either copied src/tactics_code/ or the package contents directly in src/.
if [[ -f "$P3_ROOT/src/tactics_code/__init__.py" ]]; then
  export PYTHONPATH="$P3_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
elif [[ -f "$P3_ROOT/src/__init__.py" ]]; then
  mkdir -p "$P3_SCRATCH/python"
  ln -sfn "$P3_ROOT/src" "$P3_SCRATCH/python/tactics_code"
  export PYTHONPATH="$P3_SCRATCH/python${PYTHONPATH:+:$PYTHONPATH}"
else
  echo 'Package not found: copy tactics_code/ to tactics/src/ or tactics/src/tactics_code/.' >&2
  exit 2
fi
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4
export MPLCONFIGDIR="$P3_SCRATCH/matplotlib" PYTHONUNBUFFERED=1
exec >> "$P3_ROOT/logs/$P3_RUN.log" 2>&1
trap 'code=$?; printf "%s [EXIT] code=%s\n" "$(date -u +%FT%TZ)" "$code"' EXIT
printf '%s [INFO] %s\n' "$(date -u +%FT%TZ)" "$P3_RUN"
common=(--output "$P3_ROOT" --run "$P3_RUN" --seed "${SEED:-42}" --fps "${FPS:-10}" --window "${WINDOW:-6}" --k "${K:-8}")
sample=(); audit_sample=(); all_frames=(); test_args=(); analysis_split=val
if [[ "$P3_MODE" == small ]]; then
  sample=(--max-replays "${MAX_REPLAYS:-300}")
  audit_sample=(--max-replays "${MAX_REPLAYS:-300}")
else
  all_frames=(--all-frames)
fi
if [[ "${EVALUATE_TEST:-0}" == 1 ]]; then
  test_args=(--evaluate-test)
  analysis_split=test
fi
# Explicit K always means a single requested K. Otherwise use the declared sweep;
# quote K_SWEEP in sbatch --export, e.g. K_SWEEP='6 8 12 16'.
k_args=()
if [[ -z "${K:-}" ]]; then
  read -r -a k_values <<< "${K_SWEEP:-6 8 12 16}"
  for k_value in "${k_values[@]}"; do
    if [[ ! "$k_value" =~ ^[0-9]+$ ]] || (( 10#$k_value < 2 )); then
      echo 'K_SWEEP must contain space-separated integers >=2' >&2
      exit 2
    fi
  done
  k_args=(--k-sweep "${k_values[@]}")
fi
python -m tactics_code.stage "${common[@]}" --data-root "$P3_DATA" --destination "$P3_SCRATCH/data" "${sample[@]}" "${all_frames[@]}"
state_args=(); audit_state=()
if [[ -n "${STATE_MAP:-}" ]]; then
  state_args=(--state-map "$STATE_MAP")
  audit_state=(--state-map "$STATE_MAP")
elif [[ "${ALLOW_HEURISTIC_LIVE:-0}" == 1 ]]; then
  state_args=(--allow-heuristic-live)
else
  state_args=(--state-map "$P3_ROOT/state_map_rlcs.json")
  audit_state=(--state-map "$P3_ROOT/state_map_rlcs.json")
fi
python -m tactics_code.audit "${common[@]}" --data-root "$P3_SCRATCH/data" "${audit_sample[@]}" "${audit_state[@]}"
# Retain the preceding current artifacts/results outside dashboard search paths.
# This prevents a measurement-gated stage from accidentally reading an old run.
mkdir -p "$P3_ARTIFACTS/previous-current-artifacts" "$P3_ARTIFACTS/previous-current-results"
for artifact in tokens pressure style; do
  if [[ -d "$P3_ROOT/artifacts/$artifact" ]]; then
    mv "$P3_ROOT/artifacts/$artifact" "$P3_ARTIFACTS/previous-current-artifacts/$artifact"
  fi
done
shopt -s nullglob
previous_results=("$P3_ROOT"/results/tokens*.json "$P3_ROOT"/results/pressure.json "$P3_ROOT"/results/style.json "$P3_ROOT"/results/confirmatory.json "$P3_ROOT"/results/exploratory.json)
for result in "${previous_results[@]}"; do
  if [[ -f "$result" ]]; then
    mv "$result" "$P3_ARTIFACTS/previous-current-results/"
  fi
done
shopt -u nullglob
python -m tactics_code.extract "${common[@]}" --data-root "$P3_SCRATCH/data" --compact "$P3_SCRATCH/compact" --workers "${WORKERS:-4}" --shard-replays 250 "${sample[@]}" "${state_args[@]}"
# Persist the few large derived shards. No per-replay files/checkpoints.
cp -R "$P3_SCRATCH/compact" "$P3_ARTIFACTS/compact"
python -m tactics_code.tokens "${common[@]}" --input "$P3_SCRATCH/compact" --device cuda --epochs "${EPOCHS:-20}" "${k_args[@]}" --bootstrap "${BOOTSTRAP:-2000}" --nulls "${NULLS:-999}" "${test_args[@]}"
python -m tactics_code.pressure "${common[@]}" --input "$P3_SCRATCH/compact" --split "$analysis_split" --bootstrap "${BOOTSTRAP:-2000}"
python -m tactics_code.style "${common[@]}" --input "$P3_SCRATCH/compact" --tokens "$P3_ROOT/artifacts/tokens/windows.parquet" --split "$analysis_split" --bootstrap "${BOOTSTRAP:-2000}"
python -m tactics_code.viz "${common[@]}" --split "$analysis_split"
# Preserve this run's frozen models and analytic artifacts before a future run.
for artifact in tokens pressure style; do
  if [[ -d "$P3_ROOT/artifacts/$artifact" ]]; then
    cp -R "$P3_ROOT/artifacts/$artifact" "$P3_ARTIFACTS/$artifact"
  fi
done
