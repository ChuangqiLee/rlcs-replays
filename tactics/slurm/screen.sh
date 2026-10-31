#!/bin/bash
#SBATCH --job-name=rlcs-screen
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=32
#SBATCH --ntasks=1
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=logs/screen-%j.log
#SBATCH --error=logs/screen-%j.log
# Runtime estimate is documented in docs/screen.md from the six-replay/one-worker smoke.
# Submit from tactics/ after mkdir -p logs. CPU only; no automatic sbatch.
set -eo pipefail
: "${SLURM_JOB_ID:?Submit with sbatch; do not run the full screen on a login node}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
export TACT="$HOME/workspace/rlcs-replays/tactics"
cd "$TACT"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
unset PACK
source "$TACT/slurm/env.sh"
SCREEN_SOURCE="$TACT/artifacts/p3-small-41104720-s42-w6-f10-ksweep/compact"
SCREEN_SCRATCH="$TMPDIR/screen-$SLURM_JOB_ID"
mkdir "$SCREEN_SCRATCH"
mkdir "$SCREEN_SCRATCH/compact"
# Explicit development allowlist: NEVER open/copy split 2026 (test).
cp "$SCREEN_SOURCE/extraction.json" "$SCREEN_SCRATCH/compact/extraction.json"
for season in rlcs-21-22 rlcs-22-23 rlcs-2024 rlcs-2025; do
    cp -a "$SCREEN_SOURCE/$season" "$SCREEN_SCRATCH/compact/"
done
python -m tactics_code.screen \
    --input "$SCREEN_SCRATCH/compact" \
    --output "$TACT" \
    --scratch "$SCREEN_SCRATCH" \
    --workers "$SLURM_CPUS_PER_TASK" \
    --bootstrap-reps 2000 \
    --run "screen-$SLURM_JOB_ID"

