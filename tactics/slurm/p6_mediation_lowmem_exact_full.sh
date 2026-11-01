#!/usr/bin/env bash
#SBATCH --job-name=p6-lowmem-full
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=256G
#SBATCH --time=24:00:00
#SBATCH --output=logs/p6-lowmem-full-%j.log
#SBATCH --error=logs/p6-lowmem-full-%j.log
# P6.4 boost_mediation FULL, --lowmem with bit-exact CR1.  Submitted with
# --dependency=afterok:<p6-exact-equiv>, so it only starts if the strict
# medium gate passed.  Time: medium total 872 s (analysis 205 s) for 6,000
# replays; full x6.78 -> ~1.6 h if linear; bootstrap scales with G*q^2, so
# 24 h.  256G: features ~21 GiB float32 at x6.78 rows plus reference CR1 copies (<=24*G*(q+3)^2 B), see OOM_EVAL.md.
set -euo pipefail
: "${SLURM_JOB_ID:?Batch allocation required}"
: "${TMPDIR:?Disk-backed node scratch required}"
cd "${TACT:-${SLURM_SUBMIT_DIR:-.}}"
set +u; unset PACK; source slurm/env.sh; set -u
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
scratch_fs=$(findmnt -n -o FSTYPE -T "$TMPDIR")
if [[ -z "$scratch_fs" || "$scratch_fs" == tmpfs || "$scratch_fs" == ramfs ]]; then
    echo "Refusing tmpfs scratch" >&2; exit 1
fi
# Development seasons only (events.ALLOWED_SEASONS guard); 2026 test never read.
python -c "from tactics_code.events import ALLOWED_SEASONS as s; assert not any(\"2026\" in x for x in s), s; print(\"allowed\", s)"
run="$PWD/artifacts/p6-lowmem-full-$SLURM_JOB_ID"; scratch="$TMPDIR/p6-lowmem-full-$SLURM_JOB_ID"
mkdir -p "$PWD/artifacts"; mkdir "$run" "$scratch" "$scratch/joblib"
export JOBLIB_TEMP_FOLDER="$scratch/joblib"
git rev-parse HEAD > "$run/source_commit.txt"
sha256sum src/tactics_code/boost_mediation_lowmem_exact.py src/tactics_code/boost_mediation.py src/tactics_code/lowmem.py > "$run/exact_sources.sha256"
/usr/bin/time -v -o "$run/resource.txt" python -m tactics_code.boost_mediation_lowmem_exact --lowmem \
    --workers "$SLURM_CPUS_PER_TASK" \
    --compact "$PWD/artifacts/p3-extractfull-41105069-s42-w6-f10/compact" \
    --data-root "$HOME/workspace/rlcs-replays/data" --state-map "$PWD/state_map_rlcs.json" \
    --scratch "$scratch" --artifacts "$run" --out "$run/result.json"
