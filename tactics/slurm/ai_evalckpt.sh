#!/bin/bash
#SBATCH --job-name=ai-evalckpt
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=01:30:00
#SBATCH --output=logs/ai-evalckpt-%j.log
#SBATCH --error=logs/ai-evalckpt-%j.log
# Evaluate saved fingerprint checkpoints on the shared benchmark. Usage:
#   AI_CACHE=<cache> AI_CKPTS="path1 path2" [AI_MODE=dev|final] [AI_BOOTSTRAP=200] sbatch slurm/ai_evalckpt.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${AI_CACHE:?Set AI_CACHE}"
: "${AI_CKPTS:?Set AI_CKPTS to checkpoint paths}"
AI_MODE="${AI_MODE:-dev}"
AI_BOOTSTRAP="${AI_BOOTSTRAP:-200}"
cd "$SLURM_SUBMIT_DIR"
export TACT="$PWD"
CACHE="$TACT/artifacts/ai_cache/$AI_CACHE"
case "$CACHE" in *2026*|*/test|*/test/*) printf 'forbidden cache path\n' >&2; exit 2 ;; esac
export PACK= REBUILD=
source "$TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
OUT="$TACT/results/ai_dev/$SLURM_JOB_ID"
SCRATCH="$TMPDIR/ai-evalckpt-$SLURM_JOB_ID"
mkdir -p "$OUT" "$SCRATCH"
ARGS=()
for c in $AI_CKPTS; do ARGS+=(--checkpoint "$c"); done
printf 'Source commit: '; git rev-parse HEAD
printf 'Mode: %s\nCheckpoints: %s\n' "$AI_MODE" "$AI_CKPTS"
python -B -m ai_experiments.evalckpt --cache "$CACHE" --scratch "$SCRATCH" --out "$OUT" \
    --mode "$AI_MODE" --bootstrap "$AI_BOOTSTRAP" --device cuda "${ARGS[@]}"
rm -rf "$SCRATCH"
