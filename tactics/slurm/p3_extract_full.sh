#!/bin/bash
#SBATCH --job-name=rlcs-p3-extract-full
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/p3-extract-full-%j.log
#SBATCH --error=logs/p3-extract-full-%j.log
set -eo pipefail  # match p3_pipeline.sh; Bash 4.2 empty-array convention

P3X_TACT="$HOME/workspace/rlcs-replays/tactics"
P3X_DATA="${DATA_ROOT:-/home/c.li16@students.uu.nl/workspace/rlcs-replays/data}"
P3X_JOB="${SLURM_JOB_ID:-dry-run}"
P3X_RUN="p3-extractfull-$P3X_JOB-s42-w6-f10"
P3X_OUTPUT="$HOME/workspace/rlcs-replays/analysis/p3-extract-full-$P3X_JOB"
P3X_ARTIFACTS="$P3X_TACT/artifacts/$P3X_RUN"
P3X_SCRATCH="${TMPDIR:-/node-local/TMPDIR}/$P3X_RUN"
P3X_MODE="${P3X_STAGE_MODE:-season}"
# sbatch executes a spool copy: BASH_SOURCE is not the installed slurm/ directory.
P3X_SUPPORT="$P3X_TACT/slurm/p3_extract_full_support.py"
case "$P3X_MODE" in season|full) ;; *) echo 'P3X_STAGE_MODE must be season or full' >&2; exit 2 ;; esac
show() { printf ' +'; printf ' %q' "$@"; printf '\n'; }

# This branch deliberately precedes mkdir, flock, source env.sh and EVERY Python
# invocation. It is safe on a Mac without Slurm, quota tools, or the live data.
if [[ "${P3X_DRY_RUN:-0}" == 1 ]]; then
  show df -h "$HOME" "${TMPDIR:-/node-local/TMPDIR}"
  show du -sh "$P3X_TACT/artifacts" "$P3X_DATA/frames/fps30"
  printf 'Require filesystem AND quota headroom >= 80 GB; fail closed if quota is unknown.\n'
  printf 'Acquire FD 9 with flock -n on %s and hold through publication.\n' "$P3X_TACT/status/p3-pipeline.lock"
  show source "$P3X_TACT/slurm/env.sh"
  show python "$P3X_SUPPORT" --data-root "$P3X_DATA" --output "$P3X_OUTPUT" --scratch "$P3X_SCRATCH" --artifacts "$P3X_ARTIFACTS" --run "$P3X_RUN" --mode "$P3X_MODE"
  if [[ "$P3X_MODE" == season ]]; then
    printf 'For EACH season discovered from ALL indexes (including the held-out season):\n'
    P3X_UNIT='<season>'
    P3X_SOURCE="$P3X_SCRATCH/<season>/source-view"
  else
    P3X_UNIT=all
    P3X_SOURCE="$P3X_DATA"
  fi
  P3X_DEST="$P3X_SCRATCH/$P3X_UNIT/data"
  common=(--output "$P3X_OUTPUT" --run "$P3X_RUN-$P3X_UNIT" --seed 42 --fps 10 --window 6 --k 8)
  show python -m tactics_code.stage "${common[@]}" --data-root "$P3X_SOURCE" --destination "$P3X_DEST" --all-frames
  show python -m tactics_code.audit "${common[@]}" --data-root "$P3X_DEST" --state-map "$P3X_OUTPUT/state_map_rlcs.json"
  show python -m tactics_code.extract "${common[@]}" --data-root "$P3X_DEST" --compact "$P3X_SCRATCH/$P3X_UNIT/compact" --workers 16 --shard-replays 250 --state-map "$P3X_OUTPUT/state_map_rlcs.json"
  printf 'Verify and copy completed season shards; remove only this job unit scratch.\n'
  printf 'Merge manifests, validate inventory, publish extraction.json last: %s/compact\n' "$P3X_ARTIFACTS"
  exit 0
fi

: "${SLURM_JOB_ID:?Submit with sbatch; use P3X_DRY_RUN=1 for a local command preview}"
: "${TMPDIR:?SLURM must provide node-local TMPDIR}"
[[ "${SLURM_CPUS_PER_TASK:-16}" == 16 ]] || { echo 'This script requires 16 CPUs per task' >&2; exit 2; }
[[ -f "$P3X_SUPPORT" ]] || { echo "Missing companion helper: $P3X_SUPPORT" >&2; exit 2; }
[[ -f "$P3X_TACT/state_map_rlcs.json" ]] || { echo 'Missing state_map_rlcs.json' >&2; exit 2; }
[[ -d "$P3X_TACT/status" ]] || { echo 'Missing tactics/status; preserve the existing pipeline lock location' >&2; exit 2; }
cd "$P3X_TACT"
# Same inode/location and nonblocking semantics as p3_pipeline.sh. Never unlink.
exec 9> "$P3X_TACT/status/p3-pipeline.lock"
if ! flock -n 9; then
  echo 'Another P3 pipeline owns the current dashboard artifacts; submit after it finishes.' >&2
  exit 75
fi
for path in "$P3X_OUTPUT" "$P3X_ARTIFACTS" "$P3X_SCRATCH"; do
  [[ ! -e "$path" ]] || { echo "Run path already exists: $path; use a fresh job" >&2; exit 2; }
done
printf '%s [INFO] storage preflight\n' "$(date -u +%FT%TZ)"
df -h "$HOME" "$TMPDIR"
du -sh "$P3X_TACT/artifacts" "$P3X_DATA/frames/fps30"
P3X_FREE_KIB=$(df -Pk "$HOME" | awk 'END {print $4}')
if [[ ! "$P3X_FREE_KIB" =~ ^[0-9]+$ ]] || (( P3X_FREE_KIB * 1024 < 80 * 1000 * 1000 * 1000 )); then
  echo 'HOME filesystem free space is below 80 GB (or unreadable); stopping before environment setup/staging.' >&2
  exit 2
fi
# quota(1) may be absent/unsupported for the HOME filesystem. The helper requires
# a matching local report or fresh operator-supplied remaining-quota bytes.
# The cheap override check can also fail before unpacking the environment.
if [[ -n "${P3X_HOME_QUOTA_FREE_BYTES:-}" ]]; then
  if [[ ! "$P3X_HOME_QUOTA_FREE_BYTES" =~ ^[0-9]+$ ]] ||
     ! awk -v q="$P3X_HOME_QUOTA_FREE_BYTES" 'BEGIN {exit !(q >= 80*1000*1000*1000)}'; then
    echo 'HOME remaining quota is below 80 GB (or invalid); stopping.' >&2
    exit 2
  fi
fi
# Reuse the supplied environment convention; force TACT to the existing install.
export TACT="$P3X_TACT"
source "$P3X_TACT/slurm/env.sh"
mkdir -p "$P3X_SCRATCH"
if [[ -f "$P3X_TACT/src/tactics_code/__init__.py" ]]; then
  export PYTHONPATH="$P3X_TACT/src${PYTHONPATH:+:$PYTHONPATH}"
elif [[ -f "$P3X_TACT/src/__init__.py" ]]; then
  mkdir -p "$P3X_SCRATCH/python"
  ln -s "$P3X_TACT/src" "$P3X_SCRATCH/python/tactics_code"
  export PYTHONPATH="$P3X_SCRATCH/python${PYTHONPATH:+:$PYTHONPATH}"
else
  echo 'Package not found under tactics/src' >&2; exit 2
fi
# One numerical-library thread per worker avoids oversubscribing the allocation.
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export MPLCONFIGDIR="$P3X_SCRATCH/matplotlib" PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES=''
trap 'code=$?; printf "%s [EXIT] code=%s\n" "$(date -u +%FT%TZ)" "$code"' EXIT
python "$P3X_SUPPORT" --data-root "$P3X_DATA" --output "$P3X_OUTPUT" \
  --scratch "$P3X_SCRATCH" --artifacts "$P3X_ARTIFACTS" --run "$P3X_RUN" --mode "$P3X_MODE"
