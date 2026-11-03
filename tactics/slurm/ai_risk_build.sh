#!/bin/bash
#SBATCH --job-name=ai-risk-build
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=03:00:00
#SBATCH --output=logs/ai-risk-build-%j.log
#SBATCH --error=logs/ai-risk-build-%j.log
# Build the prospective goal-risk dataset (frames, anchors, labels, snapshot features).
#   AI_COMPACT=<compact dir> AI_RISK_NAME=<name> sbatch slurm/ai_risk_build.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${AI_COMPACT:?Set AI_COMPACT to the approved compact source}"
: "${AI_RISK_NAME:?Set AI_RISK_NAME}"
case "$AI_COMPACT" in
    *2026*|*/test|*/test/*) printf '2026/test compact paths are forbidden.\n' >&2; exit 2 ;;
esac
cd "$SLURM_SUBMIT_DIR"
export TACT="$PWD"
test -f "$TACT/envs/dlenv.tar.gz" || { printf 'envs/dlenv.tar.gz required\n' >&2; exit 2; }
export PACK= REBUILD=
source "$TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
OUT="$TACT/artifacts/ai_risk/$AI_RISK_NAME"
if [ -e "$OUT" ]; then printf 'Dataset exists: %s\n' "$OUT" >&2; exit 2; fi
mkdir -p "$TACT/artifacts/ai_risk"
printf 'Source commit: '; git rev-parse HEAD
printf 'Compact: %s\nOut: %s\n' "$AI_COMPACT" "$OUT"
python -B -m ai_experiments.risk_data --compact "$AI_COMPACT" --out "$OUT" --workers "$SLURM_CPUS_PER_TASK"
du -sh "$OUT"
