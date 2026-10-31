#!/bin/bash
#SBATCH --job-name=rlcs-p6-variants
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=1
#SBATCH --ntasks=1
#SBATCH --mem=16G
#SBATCH --time=00:20:00
#SBATCH --output=logs/p6-variants-%j.log
#SBATCH --error=logs/p6-variants-%j.log
# CPU only; serial NumPy/BLAS inference, no unearned parallel speedup.
# Time is generated from local synthetic measurements by tools/estimate_runtime.py.
# See docs/P6_variants_implementation.md and artifacts/runtime_estimate.json.
# This file is prepared only; it never submits another job.
set -eo pipefail
: "${SLURM_JOB_ID:?Submit with sbatch; a compute allocation is required}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
export TACT="${TACT:-$HOME/workspace/rlcs-replays/tactics}"
cd "$TACT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
unset PACK
test -f "$TACT/envs/dlenv.tar.gz" || { echo "Missing packed project environment"; exit 1; }
source "$TACT/slurm/env.sh"
set -u
# Preserve the P4 compact precedence, with an optional task-specific override.
P6_MEDIUM="$TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact"
P6_SMALL="$TACT/artifacts/p3-small-41104720-s42-w6-f10-ksweep/compact"
if [[ -n "${P6_COMPACT:-}" ]]; then
    P6_SOURCE="$P6_COMPACT"
elif [[ -n "${P4_COMPACT:-}" ]]; then
    P6_SOURCE="$P4_COMPACT"
elif [[ -d "$P6_MEDIUM" ]]; then
    P6_SOURCE="$P6_MEDIUM"
else
    P6_SOURCE="$P6_SMALL"
fi
P6_SCRATCH="$TMPDIR/p6-variants-$SLURM_JOB_ID"
P6_ARTIFACTS="$TACT/artifacts/p6-variants-$SLURM_JOB_ID"
mkdir "$P6_SCRATCH" "$P6_ARTIFACTS"
mkdir "$P6_SCRATCH/compact"
# Check every copied path and resolved symlink before copying. Only validation
# is needed: there are no learned thresholds and no training arrays are opened.
python - "$P6_SOURCE" <<'PY'
import sys
from tactics_code.events import guard_path
from tactics_code.pressure_variants import VAL_SEASON, inventory

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
check_tree(root / VAL_SEASON)
inventory(root)  # Reject forbidden/mismatched metadata before copying arrays.
PY
cp -L "$P6_SOURCE/extraction.json" "$P6_SCRATCH/compact/extraction.json"
cp -aL "$P6_SOURCE/rlcs-2025" "$P6_SCRATCH/compact/"
git rev-parse HEAD > "$P6_ARTIFACTS/source_commit.txt"
printf '%s\n' "$P6_SOURCE" > "$P6_ARTIFACTS/compact_source.txt"
python -m tactics_code.pressure_variants \
    --compact "$P6_SCRATCH/compact" \
    --artifacts "$P6_ARTIFACTS" \
    --out "$TACT/results/p6_variants.json"
