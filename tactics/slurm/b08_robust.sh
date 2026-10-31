#!/bin/bash
#SBATCH --job-name=rlcs-b08-robust
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=16
#SBATCH --ntasks=1
#SBATCH --mem=64G
#SBATCH --time=01:30:00
#SBATCH --output=logs/b08-robust-%j.log
#SBATCH --error=logs/b08-robust-%j.log
# Estimate: screen_v2 (18 ideas, 32 cpus) took 15.3 min; B08 = 3 seeds x 14 variants + 3 shift nulls,
# each 2,000 series bootstraps, at 16 cpus -> ~40-50 min; 90 min limit (~1.8-2x). CPU only.
set -eo pipefail
: "${SLURM_JOB_ID:?sbatch only}"; : "${TMPDIR:?}"
export TACT="${TACT:-$HOME/workspace/rlcs-replays/tactics}"; cd "$TACT"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
unset PACK
source "$TACT/slurm/env.sh"
set -u
SRC="$TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact"
SCR="$TMPDIR/b08-robust-$SLURM_JOB_ID"; mkdir -p "$SCR/compact"
cp "$SRC/extraction.json" "$SCR/compact/"
for season in rlcs-21-22 rlcs-22-23 rlcs-2024 rlcs-2025; do cp -a "$SRC/$season" "$SCR/compact/"; done
python -m tactics_code.b08_robust --self-test
python -m tactics_code.b08_robust --input "$SCR/compact" --output "$TACT" --scratch "$SCR" --workers "$SLURM_CPUS_PER_TASK"
