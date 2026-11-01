#!/usr/bin/env bash
# DRAFT ONLY. Four sequential MEDIUM runs; explicit input, no source fallback.
# 64 CPUh timeout ceiling, NOT a prediction; see OOM_EVAL.md for combined cost.
#SBATCH --job-name=lowmem-equiv
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=192G
#SBATCH --time=16:00:00
#SBATCH --output=logs/lowmem-equiv-%j.log
#SBATCH --error=logs/lowmem-equiv-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Batch allocation required}"
: "${TMPDIR:?Disk-backed scratch required}"
: "${MEDIUM_COMPACT:?Explicit completed medium compact source required}"
: "${MEDIUM_DATA_ROOT:?Explicit native data root required}"
: "${MEDIUM_STATE_MAP:?Explicit state map required}"
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
    echo 'Refusing tmpfs scratch' >&2; exit 1
fi
root="$PWD/artifacts/lowmem-equiv-$SLURM_JOB_ID"
scratch="$TMPDIR/lowmem-equiv-$SLURM_JOB_ID"
mkdir -p "$PWD/artifacts"
mkdir "$root" "$scratch"
git rev-parse HEAD > "$root/source_commit.txt"
"${LOWMEM_PYTHON:-python}" -m pip freeze > "$root/environment.txt"
for task in p4 p6; do
    if [[ "$task" == p4 ]]; then module=pushup_possession; else module=boost_mediation; fi
    for variant in reference candidate; do
        run="$root/$task-$variant"
        work="$scratch/$task-$variant"
        mkdir "$run" "$work"
        mkdir "$work/joblib"
        export JOBLIB_TEMP_FOLDER="$work/joblib"
        flags=()
        if [[ "$variant" == candidate ]]; then flags+=(--lowmem); fi
        /usr/bin/time -v -o "$run/resource.txt" "${LOWMEM_PYTHON:-python}" \
            -m "tactics_code.$module" "${flags[@]}" \
            --workers "${SLURM_CPUS_PER_TASK:-4}" --compact "$MEDIUM_COMPACT" \
            --data-root "$MEDIUM_DATA_ROOT" --state-map "$MEDIUM_STATE_MAP" \
            --scratch "$work" --artifacts "$run" --out "$run/result.json"
    done
    "${LOWMEM_PYTHON:-python}" -m tactics_code.lowmem_compare --task "$task" \
        --reference "$root/$task-reference" --candidate "$root/$task-candidate" \
        --out "$root/$task-equivalence.json"
done
