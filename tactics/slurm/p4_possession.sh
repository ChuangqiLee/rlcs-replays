#!/bin/bash
#SBATCH --job-name=rlcs-p4-possession
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=32
#SBATCH --ntasks=1
#SBATCH --mem=64G
#SBATCH --time=01:40:00
#SBATCH --output=logs/p4-possession-%j.log
#SBATCH --error=logs/p4-possession-%j.log
# CPU only. Shard workers use one thread; three fold fits plus the final fit
# use at most four processes with eight inner threads each.
# 40-replay smoke: 121.835 s; phase scaling to 6,000: 51.213 min.
# 1.6x compute + 15 min staging = 96.941 min, rounded up to 01:40:00.
# Derivation and measured phases: docs/P4_possession_implementation.md.
# Never auto-sbatch. Analysis constants are fixed in pushup_possession.py.
set -eo pipefail
: "${SLURM_JOB_ID:?Submit this script with sbatch; full runs are not login-node work}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
export TACT="${TACT:-$HOME/workspace/rlcs-replays/tactics}"
cd "$TACT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
P4_WORKERS="${SLURM_CPUS_PER_TASK:-32}"
unset PACK
test -f "$TACT/envs/dlenv.tar.gz" || { echo "Missing packed project environment"; exit 1; }
source "$TACT/slurm/env.sh"
set -u
# Same compact source selection as slurm/p4_dr.sh.
P4_MEDIUM="$TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact"
P4_SMALL="$TACT/artifacts/p3-small-41104720-s42-w6-f10-ksweep/compact"
if [[ -n "${P4_COMPACT:-}" ]]; then
    P4_SOURCE="$P4_COMPACT"
elif [[ -d "$P4_MEDIUM" ]]; then
    P4_SOURCE="$P4_MEDIUM"
else
    P4_SOURCE="$P4_SMALL"
fi
P4_SCRATCH="$TMPDIR/p4-possession-$SLURM_JOB_ID"
P4_ARTIFACTS="$TACT/artifacts/p4-possession-$SLURM_JOB_ID"
mkdir "$P4_SCRATCH" "$P4_ARTIFACTS"
mkdir "$P4_SCRATCH/compact" "$P4_SCRATCH/arrays" "$P4_SCRATCH/joblib"
export JOBLIB_TEMP_FOLDER="$P4_SCRATCH/joblib"
# Check every copied path and resolved symlink target BEFORE copying. Explicit
# season traversal never discovers or opens a held-out root directory.
python - "$P4_SOURCE" <<'PY'
import sys
from tactics_code.events import guard_path, ALLOWED_SEASONS

def check_tree(path, ancestors=frozenset()):
    path = guard_path(path)
    if path.is_dir():
        resolved = path.resolve()
        if resolved in ancestors:
            raise SystemExit('Compact symlink cycle: ' + str(path))
        for child in path.iterdir():
            check_tree(child, ancestors | {resolved})
    elif not path.is_file():
        raise SystemExit('Missing/nonregular compact input: ' + str(path))

root = guard_path(sys.argv[1])
check_tree(root / 'extraction.json')
for season in ALLOWED_SEASONS:
    directory = guard_path(root / season)
    if not directory.is_dir():
        raise SystemExit('Missing development season: ' + season)
    check_tree(directory)
PY
cp -L "$P4_SOURCE/extraction.json" "$P4_SCRATCH/compact/extraction.json"
for season in rlcs-21-22 rlcs-22-23 rlcs-2024 rlcs-2025; do
    # Dereference checked links so analysis arrays actually reside on TMPDIR.
    cp -aL "$P4_SOURCE/$season" "$P4_SCRATCH/compact/"
done
git rev-parse HEAD > "$P4_ARTIFACTS/source_commit.txt"
printf '%s\n' "$P4_SOURCE" > "$P4_ARTIFACTS/compact_source.txt"
python -m tactics_code.pushup_possession \
    --workers "$P4_WORKERS" \
    --compact "$P4_SCRATCH/compact" \
    --scratch "$P4_SCRATCH/arrays" \
    --artifacts "$P4_ARTIFACTS" \
    --out "$TACT/results/pushup_possession.json" \
    --state-map "$TACT/state_map_rlcs.json"
