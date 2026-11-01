#!/usr/bin/env bash
#SBATCH --job-name=p6-exact-equiv
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=192G
#SBATCH --time=03:00:00
#SBATCH --output=logs/p6-exact-equiv-%j.log
#SBATCH --error=logs/p6-exact-equiv-%j.log
# Re-validate P6 lowmem with the bit-exact CR1 (boost_mediation_lowmem_exact)
# on the SAME medium inputs as 41114791, against its existing p6-reference.
# Exits non-zero unless the strict gate (atol 1e-12, rtol 1e-10) passes.
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
ref="$PWD/artifacts/lowmem-equiv-41114791/p6-reference"
run="$PWD/artifacts/p6-exact-equiv-$SLURM_JOB_ID"; scratch="$TMPDIR/p6-exact-$SLURM_JOB_ID"
mkdir "$run" "$scratch" "$scratch/joblib"; export JOBLIB_TEMP_FOLDER="$scratch/joblib"
git rev-parse HEAD > "$run/source_commit.txt"; sha256sum src/tactics_code/boost_mediation_lowmem_exact.py src/tactics_code/boost_mediation.py src/tactics_code/lowmem.py > "$run/exact_sources.sha256"; python -m pip freeze > "$run/environment.txt"
cmp <(grep -v '^#' "$run/environment.txt") <(grep -v '^#' artifacts/lowmem-equiv-41114791/environment.txt) \
    || { echo "environment differs from 41114791; stop" >&2; exit 1; }
/usr/bin/time -v -o "$run/resource.txt" python -m tactics_code.boost_mediation_lowmem_exact --lowmem \
    --workers "$SLURM_CPUS_PER_TASK" \
    --compact "$PWD/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact" \
    --data-root "$HOME/workspace/rlcs-replays/data" --state-map "$PWD/state_map_rlcs.json" \
    --scratch "$scratch" --artifacts "$run" --out "$run/result.json"
python tools/p6_full_compare.py "$ref" "$run" > "$run.fullcompare.json" || true
python -m tactics_code.lowmem_compare --task p6 --reference "$ref" --candidate "$run" \
    --out "$run.strict.json"
