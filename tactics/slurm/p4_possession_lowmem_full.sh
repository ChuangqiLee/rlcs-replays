#!/usr/bin/env bash
#SBATCH --job-name=p4-lowmem-full
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=384G
#SBATCH --time=36:00:00
#SBATCH --output=logs/p4-lowmem-full-%j.log
#SBATCH --error=logs/p4-lowmem-full-%j.log
# P4 pushup_possession FULL, --lowmem (bit-identical to reference on medium,
# job 41114791: max abs/rel error 0).  Time: medium lowmem 6,000 replays took
# 3,735 s; full = 40,683 selected replays (x6.78) -> ~7.0 h if linear; 36 h
# allows ~5x for superlinear HGB / larger identity vocabulary.  384G (of ~503 GB node): single
# fit, see OOM_EVAL.md.  Inputs fixed to the full compact used by 41105136.
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
FULL_COMPACT="$PWD/artifacts/p3-extractfull-41105069-s42-w6-f10/compact"
DATA_ROOT="$HOME/workspace/rlcs-replays/data"
STATE_MAP="$PWD/state_map_rlcs.json"
run="$PWD/artifacts/p4-lowmem-full-$SLURM_JOB_ID"; scratch="$TMPDIR/p4-lowmem-full-$SLURM_JOB_ID"
mkdir -p "$PWD/artifacts"; mkdir "$run" "$scratch" "$scratch/joblib"
export JOBLIB_TEMP_FOLDER="$scratch/joblib"
git rev-parse HEAD > "$run/source_commit.txt"
/usr/bin/time -v -o "$run/resource.txt" python -m tactics_code.pushup_possession --lowmem \
    --workers "$SLURM_CPUS_PER_TASK" --compact "$FULL_COMPACT" \
    --data-root "$DATA_ROOT" --state-map "$STATE_MAP" \
    --scratch "$scratch" --artifacts "$run" --out "$run/result.json"
