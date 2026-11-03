#!/bin/bash
#SBATCH --job-name=ai-smoke
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=00:20:00
#SBATCH --output=logs/ai-smoke-%j.log
#SBATCH --error=logs/ai-smoke-%j.log
# Synthetic fixtures only; run from the repository after mkdir -p logs.
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
export AI_START_EPOCH="$(date +%s)"
AI_TACT="${AI_TACT:-$SLURM_SUBMIT_DIR}"
cd "$AI_TACT"
AI_TACT="$PWD"
export TACT="$AI_TACT"
AI_OUTPUT="$AI_TACT/results/ai/$SLURM_JOB_ID"
AI_SCRATCH="$TMPDIR/ai-smoke-$SLURM_JOB_ID"
# mkdir without -p on the final directories refuses to overwrite previous runs.
mkdir -p "$AI_TACT/results/ai" "$AI_TACT/logs"
mkdir "$AI_OUTPUT" "$AI_SCRATCH"
ai_finish() {
    ai_status=$?
    trap - EXIT
    printf '{"exit_code":%s,"phase":"synthetic_smoke","synthetic":true,"test_opened":false}\n' \
        "$ai_status" > "$AI_OUTPUT/exit_status.json"
    exit "$ai_status"
}
trap ai_finish EXIT
# A smoke tests our code, not an unbounded package build. Prepare envs/dlenv.tar.gz
# using the existing environment workflow before submitting if it is absent.
test -f "$AI_TACT/envs/dlenv.tar.gz" || {
    printf 'The <=20-minute smoke requires the existing envs/dlenv.tar.gz.\n' >&2
    exit 2
}
export PACK= REBUILD=
source "$AI_TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export PYTHONPATH="$AI_TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}" VECLIB_MAXIMUM_THREADS=1
printf 'Source commit: '
git rev-parse HEAD
python -B -c 'import torch; assert torch.cuda.is_available(), "A CUDA GPU is required"; print("Torch", torch.__version__, "CUDA", torch.version.cuda, "GPU", torch.cuda.get_device_name(0))'
python -B -m ai_experiments --smoke --device cuda \
    --out-dir "$AI_OUTPUT" --scratch "$AI_SCRATCH"
