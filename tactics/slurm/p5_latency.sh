#!/bin/bash
#SBATCH --job-name=rlcs-p5-latency
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=1
#SBATCH --ntasks=1
#SBATCH --mem=16G
#SBATCH --time=00:35:00
#SBATCH --output=logs/p5-latency-%j.log
#SBATCH --error=logs/p5-latency-%j.log
# CPU-only serial inference; tools/estimate_runtime.py generates the walltime.
# Prepared script only; no submission or remote connection is performed here.
set -eo pipefail
: "${SLURM_JOB_ID:?A compute allocation is required}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
export TACT="${TACT:-$HOME/workspace/rlcs-replays/tactics}"
cd "$TACT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH="$TACT/src"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
unset PACK
test -f "$TACT/envs/dlenv.tar.gz" || { echo "Missing packed project environment"; exit 1; }
source "$TACT/slurm/env.sh"
set -u
P5_MEDIUM="$TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact"
P5_SMALL="$TACT/artifacts/p3-small-41104720-s42-w6-f10-ksweep/compact"
if [[ -n "${P5_COMPACT:-}" ]]; then
    P5_SOURCE="$P5_COMPACT"
elif [[ -n "${P4_COMPACT:-}" ]]; then
    P5_SOURCE="$P4_COMPACT"
elif [[ -d "$P5_MEDIUM" ]]; then
    P5_SOURCE="$P5_MEDIUM"
else
    P5_SOURCE="$P5_SMALL"
fi
P5_SCRATCH="$TMPDIR/p5-latency-$SLURM_JOB_ID"
P5_ARTIFACTS="$TACT/artifacts/p5-latency-$SLURM_JOB_ID"
mkdir "$P5_SCRATCH" "$P5_ARTIFACTS"
mkdir "$P5_SCRATCH/compact"
python - "$P5_SOURCE" <<'PY'
import sys
from tactics_code.events import guard_path
from tactics_code.rotation_latency import VAL_SEASON, inventory

def check_tree(path, ancestors=frozenset()):
    path = guard_path(path)
    if path.is_dir():
        resolved = path.resolve()
        if resolved in ancestors:
            raise SystemExit('Compact symlink cycle: ' + str(path))
        for child in path.iterdir():
            check_tree(child, ancestors | {resolved})
    elif not path.is_file():
        raise SystemExit('Missing/nonregular input: ' + str(path))

root = guard_path(sys.argv[1])
check_tree(root / 'extraction.json')
check_tree(root / VAL_SEASON)
inventory(root)
PY
cp -L "$P5_SOURCE/extraction.json" "$P5_SCRATCH/compact/extraction.json"
cp -aL "$P5_SOURCE/rlcs-2025" "$P5_SCRATCH/compact/"
git rev-parse HEAD > "$P5_ARTIFACTS/source_commit.txt"
printf '%s\n' "$P5_SOURCE" > "$P5_ARTIFACTS/compact_source.txt"
P5_ARGS=()
case "${P5_PILOT:-0}" in
    0) P5_DEFAULT_OUT="$TACT/results/p5_latency.json" ;;
    1) P5_ARGS+=(--pilot); P5_DEFAULT_OUT="$TACT/results/p5_latency_pilot.json" ;;
    *) echo "P5_PILOT must be zero or one"; exit 1 ;;
esac
if [[ -n "${P5_DATA_ROOT:-}" ]]; then
    P5_ARGS+=(--data-root "$P5_DATA_ROOT")
fi
python -m tactics_code.rotation_latency \
    --compact "$P5_SCRATCH/compact" \
    --artifacts "$P5_ARTIFACTS" --scratch "$P5_SCRATCH" \
    --state-map "${P5_STATE_MAP:-$TACT/state_map_rlcs.json}" \
    --out "${P5_OUT:-$P5_DEFAULT_OUT}" ${P5_ARGS[@]+"${P5_ARGS[@]}"}
