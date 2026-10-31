#!/bin/bash
#SBATCH --job-name=rlcs-screen-v2
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=32
#SBATCH --ntasks=1
#SBATCH --mem=64G
#SBATCH --time=01:30:00
#SBATCH --output=logs/screen-v2-%j.log
#SBATCH --error=logs/screen-v2-%j.log
# Measured 10-replay, one-worker, 2,000-replicate smoke: 28.13 seconds.
# Conservative full projection 50.5 minutes; 90 minutes is a 1.78x margin.
# Scaling, unmeasured sparse paths and acceptance evidence: docs/screen_v2.md.
# CPU only. Submit from tactics/. This script never calls sbatch.
set -eo pipefail
: "${SLURM_JOB_ID:?Submit with sbatch; full screens must not run on the login node}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
export TACT="${TACT:-$HOME/workspace/rlcs-replays/tactics}"
cd "$TACT"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export BLIS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
unset PACK
test -f "$TACT/envs/dlenv.tar.gz" || { echo 'Missing packed project environment'; exit 1; }
source "$TACT/slurm/env.sh"
set -u
SCREEN_V2_SOURCE="$TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact"
SCREEN_V2_SCRATCH="$TMPDIR/screen-v2-$SLURM_JOB_ID"
mkdir "$SCREEN_V2_SCRATCH"
mkdir "$SCREEN_V2_SCRATCH/compact"
# Guard input directories and symlink targets BEFORE copying; individual shard
# paths are guarded again before open by the compact loader.
python - "$SCREEN_V2_SOURCE" <<'PY'
import sys
from tactics_code.screen import guard_path, ALLOWED_SEASONS
root = guard_path(sys.argv[1])
guard_path(root / 'extraction.json')
for season in ALLOWED_SEASONS:
    path = guard_path(root / season)
    if not path.is_dir():
        raise SystemExit('Missing allowed development season: ' + season)
PY
cp "$SCREEN_V2_SOURCE/extraction.json" "$SCREEN_V2_SCRATCH/compact/extraction.json"
# NEVER copy/open 2026. Native goals use the same explicit development allowlist.
for season in rlcs-21-22 rlcs-22-23 rlcs-2024 rlcs-2025; do
    cp -a "$SCREEN_V2_SOURCE/$season" "$SCREEN_V2_SCRATCH/compact/"
done
python -m tactics_code.screen_v2 \
    --input "$SCREEN_V2_SCRATCH/compact" \
    --output "$TACT" \
    --scratch "$SCREEN_V2_SCRATCH" \
    --workers "$SLURM_CPUS_PER_TASK" \
    --bootstrap-reps 2000 \
    --seed 42 \
    --run "screen-v2-$SLURM_JOB_ID"
