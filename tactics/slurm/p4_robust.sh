#!/bin/bash
#SBATCH --job-name=rlcs-p4-robust
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=robust/p4-%j.log
#SBATCH --error=robust/p4-%j.log
# Submit from tactics/ after mkdir -p robust. One variant per job, never an array.
set -eo pipefail  # Cheaha bash 4.2: avoid nounset with optional/empty arrays.
: "${SLURM_JOB_ID:?Run this script with sbatch, not on a login node}"
: "${TMPDIR:?SLURM must provide node-local TMPDIR}"
if [[ -n "${SLURM_ARRAY_TASK_ID:-}" ]]; then
  echo 'Use one sbatch submission per variant, not an array.' >&2
  exit 2
fi
export TACT="$HOME/workspace/rlcs-replays/tactics"
cd "$TACT"
P4_SPLIT=val
[[ "${EVALUATE_TEST:-0}" == 1 ]] && P4_SPLIT=test
P4_VARIANT="${VARIANT:-s${SEED:-42}-k${K:-8}-w${WINDOW:-6}-f${FPS:-10}-n${MAX_REPLAYS:-300}-l${PRESSURE_LATE_SECONDS:-60}-m${PRESSURE_SCORE_MARGIN:-1}-${P4_SPLIT}}"
if [[ ! "$P4_VARIANT" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo 'VARIANT must contain only letters, digits, dot, underscore, hyphen.' >&2
  exit 2
fi
mkdir -p "$TACT/robust/.locks"
# Own lock namespace: no reads, writes or flock calls on P3's lock.
exec 9> "$TACT/robust/.locks/$P4_VARIANT.lock"
if ! flock -n 9; then
  echo "Another job owns robustness variant $P4_VARIANT" >&2
  exit 75
fi
export P4_OUTPUT="$TACT/robust/$P4_VARIANT-$SLURM_JOB_ID"
export P4_VARIANT
# Refuse overwrite/resume: a requeue must use a fresh submission/job ID.
mkdir "$P4_OUTPUT"
mkdir -p "$P4_OUTPUT/logs" "$P4_OUTPUT/results" "$P4_OUTPUT/runs" "$P4_OUTPUT/artifacts"
export P4_SCRATCH="$TMPDIR/p4-$P4_VARIANT-$SLURM_JOB_ID"
mkdir "$P4_SCRATCH"
exec >> "$P4_OUTPUT/logs/pipeline.log" 2>&1
trap 'code=$?; printf "%s [EXIT] code=%s\n" "$(date -u +%FT%TZ)" "$code"' EXIT
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}" PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR="$P4_SCRATCH/matplotlib"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
# env.sh may optionally pack a shared environment; disable that write for P4.
unset PACK
source "$TACT/slurm/env.sh"
python -m tactics_code.robust
