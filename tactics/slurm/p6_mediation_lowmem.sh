#!/usr/bin/env bash
# DRAFT ONLY: see OOM_EVAL.md; serial inference can exceed this time cap.
#SBATCH --job-name=p6-mediation-lowmem
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=192G
#SBATCH --time=06:00:00
#SBATCH --output=logs/p6-lowmem-%j.log
#SBATCH --error=logs/p6-lowmem-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Batch allocation required}"
: "${TMPDIR:?Disk-backed node scratch required}"
: "${P6_COMPACT:?Explicit development compact input required}"
: "${P6_DATA_ROOT:?Explicit native data root required}"
: "${P6_STATE_MAP:?Explicit state map required}"
cd "${TACT:-${SLURM_SUBMIT_DIR:-.}}"
if [[ -z "${LOWMEM_PYTHON:-}" ]]; then
    test -f slurm/env.sh
    set +u; unset PACK; source slurm/env.sh; set -u
fi
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
scratch_fs=$(findmnt -n -o FSTYPE -T "$TMPDIR")
if [[ -z "$scratch_fs" || "$scratch_fs" == tmpfs || "$scratch_fs" == ramfs ]]; then
    echo 'Refusing tmpfs scratch; choose node-local disk' >&2; exit 1
fi
run="$PWD/artifacts/p6-lowmem-$SLURM_JOB_ID"
scratch="$TMPDIR/p6-lowmem-$SLURM_JOB_ID"
mkdir -p "$PWD/artifacts"
mkdir "$run" "$scratch"
mkdir "$scratch/joblib"
export JOBLIB_TEMP_FOLDER="$scratch/joblib"
git rev-parse HEAD > "$run/source_commit.txt"
/usr/bin/time -v -o "$run/resource.txt" "${LOWMEM_PYTHON:-python}" \
    -m tactics_code.boost_mediation --lowmem \
    --workers "${SLURM_CPUS_PER_TASK:-8}" --compact "$P6_COMPACT" \
    --data-root "$P6_DATA_ROOT" --state-map "$P6_STATE_MAP" \
    --scratch "$scratch" --artifacts "$run" --out "$run/result.json"
