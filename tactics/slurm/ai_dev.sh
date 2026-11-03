#!/bin/bash
#SBATCH --job-name=ai-dev
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/ai-dev-%j.log
#SBATCH --error=logs/ai-dev-%j.log
# Fingerprint encoder development/final runs from the window cache. Usage:
#   AI_CACHE=<cache name> AI_PRESETS=a,b,c [AI_MODE=dev|final] [AI_DEV_SEASON=rlcs-2024]
#   [AI_OVERRIDES="--override k=v ..."] sbatch slurm/ai_dev.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${AI_CACHE:?Set AI_CACHE to a cache name under artifacts/ai_cache}"
: "${AI_PRESETS:?Set AI_PRESETS}"
AI_MODE="${AI_MODE:-dev}"
AI_DEV_SEASON="${AI_DEV_SEASON:-rlcs-2024}"
cd "$SLURM_SUBMIT_DIR"
export TACT="$PWD"
CACHE="$TACT/artifacts/ai_cache/$AI_CACHE"
case "$CACHE" in *2026*|*/test|*/test/*) printf 'forbidden cache path\n' >&2; exit 2 ;; esac
test -d "$CACHE" || { printf 'Missing cache %s\n' "$CACHE" >&2; exit 2; }
test -f "$TACT/envs/dlenv.tar.gz" || { printf 'envs/dlenv.tar.gz required\n' >&2; exit 2; }
export PACK= REBUILD=
source "$TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
OUT="$TACT/results/ai_dev/$SLURM_JOB_ID"
CKPT="$TACT/artifacts/ai_runs/$SLURM_JOB_ID"
SCRATCH="$TMPDIR/ai-dev-$SLURM_JOB_ID"
mkdir -p "$OUT" "$CKPT" "$SCRATCH"
printf 'Source commit: '; git rev-parse HEAD
printf 'Cache: %s\nMode: %s\nDev season: %s\nPresets: %s\nOverrides: %s\n' "$CACHE" "$AI_MODE" "$AI_DEV_SEASON" "$AI_PRESETS" "${AI_OVERRIDES:-}"
python -B -c 'import torch; assert torch.cuda.is_available(); print("Torch", torch.__version__, "GPU", torch.cuda.get_device_name(0))'
df -h "$TMPDIR" | tail -1
# shellcheck disable=SC2086
python -B -m ai_experiments.devrun --cache "$CACHE" --scratch "$SCRATCH" --out "$OUT" \
    --checkpoints "$CKPT" --mode "$AI_MODE" --dev-season "$AI_DEV_SEASON" \
    --presets "$AI_PRESETS" --device cuda ${AI_OVERRIDES:-}
rm -rf "$SCRATCH"
