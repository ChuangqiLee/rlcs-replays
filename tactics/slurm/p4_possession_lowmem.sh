#!/usr/bin/env bash
# DRAFT ONLY: see OOM_EVAL.md; no submission is performed by this file.
#SBATCH --job-name=p4-possession-lowmem
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=192G
#SBATCH --time=04:00:00
#SBATCH --output=logs/p4-lowmem-%j.log
#SBATCH --error=logs/p4-lowmem-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Batch allocation required}"
: "${TMPDIR:?Disk-backed node scratch required}"
: "${P4_COMPACT:?Explicit development compact input required; no fallback}"
: "${P4_DATA_ROOT:?Explicit native data root required}"
: "${P4_STATE_MAP:?Explicit state map required}"
cd "${TACT:-${SLURM_SUBMIT_DIR:-.}}"
if [[ -z "${LOWMEM_PYTHON:-}" ]]; then
    test -f slurm/env.sh
    set +u; unset PACK; source slurm/env.sh; set -u
fi
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
# A tmpfs scratch would count unpacked arrays against the memory limit.
scratch_fs=$(findmnt -n -o FSTYPE -T "$TMPDIR")
if [[ -z "$scratch_fs" || "$scratch_fs" == tmpfs || "$scratch_fs" == ramfs ]]; then
    echo 'Refusing tmpfs scratch; choose node-local disk' >&2; exit 1
fi
run="$PWD/artifacts/p4-lowmem-$SLURM_JOB_ID"
scratch="$TMPDIR/p4-lowmem-$SLURM_JOB_ID"
mkdir -p "$PWD/artifacts"
mkdir "$run" "$scratch"
mkdir "$scratch/joblib"
export JOBLIB_TEMP_FOLDER="$scratch/joblib"
git rev-parse HEAD > "$run/source_commit.txt"
# Input traversal uses the existing allowed-season guards; no entire-root copy.
# The 8 workers only extract shards; --lowmem runs 4 nuisance tasks sequentially.
/usr/bin/time -v -o "$run/resource.txt" "${LOWMEM_PYTHON:-python}" \
    -m tactics_code.pushup_possession --lowmem \
    --workers "${SLURM_CPUS_PER_TASK:-8}" --compact "$P4_COMPACT" \
    --data-root "$P4_DATA_ROOT" --state-map "$P4_STATE_MAP" \
    --scratch "$scratch" --artifacts "$run" --out "$run/result.json"
