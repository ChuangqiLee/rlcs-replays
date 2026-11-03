#!/bin/bash
#SBATCH --job-name=ai-risk
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/ai-risk-%j.log
#SBATCH --error=logs/ai-risk-%j.log
# Goal-risk history-vs-snapshot experiment. Usage:
#   AI_RISK=<dataset name> [AI_MODE=dev|final] [AI_PRESET=default] [AI_OVERRIDES="--override k=v"] sbatch slurm/ai_risk.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${AI_RISK:?Set AI_RISK to a dataset name under artifacts/ai_risk}"
AI_MODE="${AI_MODE:-dev}"
AI_PRESET="${AI_PRESET:-default}"
cd "$SLURM_SUBMIT_DIR"
export TACT="$PWD"
DATA="$TACT/artifacts/ai_risk/$AI_RISK"
case "$DATA" in *2026*|*/test|*/test/*) printf 'forbidden data path\n' >&2; exit 2 ;; esac
test -d "$DATA" || { printf 'Missing dataset %s\n' "$DATA" >&2; exit 2; }
export PACK= REBUILD=
source "$TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
OUT="$TACT/results/ai_risk/$SLURM_JOB_ID"
SCRATCH="$TMPDIR/ai-risk-$SLURM_JOB_ID"
mkdir -p "$OUT" "$SCRATCH"
printf 'Source commit: '; git rev-parse HEAD
printf 'Data: %s\nMode: %s\nPreset: %s\nOverrides: %s\n' "$DATA" "$AI_MODE" "$AI_PRESET" "${AI_OVERRIDES:-}"
python -B -c 'import torch; assert torch.cuda.is_available(); print("Torch", torch.__version__, "GPU", torch.cuda.get_device_name(0))'
# shellcheck disable=SC2086
python -B -m ai_experiments.riskrun --data "$DATA" --scratch "$SCRATCH" --out "$OUT" \
    --mode "$AI_MODE" --preset "$AI_PRESET" --device cuda ${AI_OVERRIDES:-}
rm -rf "$SCRATCH"
