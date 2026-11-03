#!/bin/bash
#SBATCH --job-name=ai-summary-metrics
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=logs/ai-summary-metrics-%j.log
#SBATCH --error=logs/ai-summary-metrics-%j.log
# Identity-supervised linear/MLP metrics on the handcrafted and channel-statistics summaries (post-freeze comparator
# for the fingerprint benchmark; no encoder training). Usage:
#   AI_CACHE=medium-w60-cap64 AI_MODE=final AI_FINAL_OK=1 sbatch slurm/ai_summary_metrics.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${AI_CACHE:?Set AI_CACHE to a cache name under artifacts/ai_cache}"
AI_MODE="${AI_MODE:-dev}"
cd "$SLURM_SUBMIT_DIR"
export TACT="$PWD"
CACHE="$TACT/artifacts/ai_cache/$AI_CACHE"
case "$CACHE" in *2026*|*/test|*/test/*) printf 'forbidden cache path\n' >&2; exit 2 ;; esac
test -d "$CACHE" || { printf 'Missing cache %s\n' "$CACHE" >&2; exit 2; }
export PACK= REBUILD=
source "$TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
OUT="$TACT/results/ai_dev/$SLURM_JOB_ID"
CKPT="$TACT/artifacts/ai_runs/$SLURM_JOB_ID"
SCRATCH="$TMPDIR/ai-summary-$SLURM_JOB_ID"
mkdir -p "$OUT" "$CKPT" "$SCRATCH"
printf 'Source commit: '; git rev-parse HEAD || true
printf 'Cache: %s\nMode: %s\n' "$CACHE" "$AI_MODE"
python -B -m ai_experiments.summary_metrics --cache "$CACHE" --scratch "$SCRATCH" --out "$OUT" --checkpoints "$CKPT" \
    --mode "$AI_MODE" --device cpu --seeds 42,43,44
rm -rf "$SCRATCH"
