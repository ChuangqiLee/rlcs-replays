#!/bin/bash
#SBATCH --job-name=rlcs-p4-dr
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=8
#SBATCH --ntasks=1
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=logs/p4-dr-%j.log
#SBATCH --error=logs/p4-dr-%j.log
# CPU only. Measured common-ten-replay/default-model smoke and conservative
# medium scaling are recorded in docs/P4_measurement_audit.md. Never auto-sbatch.
set -eo pipefail
: "${SLURM_JOB_ID:?Submit this script with sbatch; full runs are not login-node work}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
export TACT="${TACT:-$HOME/workspace/rlcs-replays/tactics}"
cd "$TACT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
unset PACK
# Existing packed project environment; this job does not train/use a GPU model.
test -f "$TACT/envs/dlenv.tar.gz" || { echo "Missing packed project environment"; exit 1; }
source "$TACT/slurm/env.sh"
set -u
P4_MEDIUM="$TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact"
P4_SMALL="$TACT/artifacts/p3-small-41104720-s42-w6-f10-ksweep/compact"
if [[ -n "${P4_COMPACT:-}" ]]; then
    P4_SOURCE="$P4_COMPACT"
elif [[ -d "$P4_MEDIUM" ]]; then
    P4_SOURCE="$P4_MEDIUM"
else
    P4_SOURCE="$P4_SMALL"
fi
P4_SCRATCH="$TMPDIR/p4-dr-$SLURM_JOB_ID"
P4_ARTIFACTS="$TACT/artifacts/p4-dr-$SLURM_JOB_ID"
mkdir "$P4_SCRATCH" "$P4_ARTIFACTS"
mkdir "$P4_SCRATCH/compact" "$P4_SCRATCH/arrays"
# Guard paths and symlink targets BEFORE copying. NEVER copy/open 2026.
python - "$P4_SOURCE" <<'PY'
import sys
from pathlib import Path
from tactics_code.events import guard_path, ALLOWED_SEASONS
root = guard_path(sys.argv[1])
guard_path(root / 'extraction.json')
for season in ALLOWED_SEASONS:
    guard_path(root / season)
    if not (root / season).is_dir():
        raise SystemExit('Missing development season: ' + season)
PY
cp "$P4_SOURCE/extraction.json" "$P4_SCRATCH/compact/extraction.json"
for season in rlcs-21-22 rlcs-22-23 rlcs-2024 rlcs-2025; do
    cp -a "$P4_SOURCE/$season" "$P4_SCRATCH/compact/"
done
git rev-parse HEAD > "$P4_ARTIFACTS/source_commit.txt"
printf '%s\n' "$P4_SOURCE" > "$P4_ARTIFACTS/compact_source.txt"
python -m tactics_code.pushup_dr \
    --compact "$P4_SCRATCH/compact" \
    --scratch "$P4_SCRATCH/arrays" \
    --artifacts "$P4_ARTIFACTS" \
    --out "$TACT/results/pushup_dr.json" \
    --state-map "$TACT/state_map_rlcs.json" \
    --folds 3 --iterations 80 --bootstrap 2000 --seed 42
