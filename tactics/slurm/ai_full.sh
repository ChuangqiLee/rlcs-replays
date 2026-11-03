#!/bin/bash
#SBATCH --job-name=ai-full
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:15:00
#SBATCH --output=logs/ai-full-%A_%a-%j.log
#SBATCH --error=logs/ai-full-%A_%a-%j.log
# Submitted by ai_submit_full.sh: a train-only diagnostic gate, then 60 array tasks.
# Each array task has a 3,000s operational cap (2,400s training); the extra SLURM
# allowance is for shutdown/report preservation, not additional training.
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${AI_COMPACT:?Set AI_COMPACT to the approved pre-2025/2025 compact source}"
export AI_START_EPOCH="$(date +%s)"
AI_PHASE="${AI_PHASE:-full}"
case "$AI_PHASE" in
    diagnose) AI_ARGS=(--diagnose) ;;
    full)
        : "${SLURM_ARRAY_TASK_ID:?Full runs require the fixed experiment array}"
        case "$SLURM_ARRAY_TASK_ID" in
            ''|*[!0-9]*) printf 'Invalid array index.\n' >&2; exit 2 ;;
        esac
        if [ "$SLURM_ARRAY_TASK_ID" -ge 60 ]; then
            printf 'Array index must be in 0..59.\n' >&2; exit 2
        fi
        AI_ARGS=(--job-index "$SLURM_ARRAY_TASK_ID") ;;
    *) printf 'AI_PHASE must be full or diagnose.\n' >&2; exit 2 ;;
esac
AI_TACT="${AI_TACT:-$SLURM_SUBMIT_DIR}"
cd "$AI_TACT"
AI_TACT="$PWD"
export TACT="$AI_TACT"
AI_OUTPUT="$AI_TACT/results/ai/$SLURM_JOB_ID"
AI_SCRATCH="$TMPDIR/ai-$SLURM_JOB_ID"
mkdir -p "$AI_TACT/results/ai" "$AI_TACT/logs"
mkdir "$AI_OUTPUT" "$AI_SCRATCH"
ai_finish() {
    ai_status=$?
    trap - EXIT
    printf '{"exit_code":%s,"phase":"%s","synthetic":false,"test_opened":false}\n' \
        "$ai_status" "$AI_PHASE" > "$AI_OUTPUT/exit_status.json"
    exit "$ai_status"
}
trap ai_finish EXIT
# Never repack or update the shared environment from an experiment job.
test -f "$AI_TACT/envs/dlenv.tar.gz" || {
    printf 'AI jobs require the existing envs/dlenv.tar.gz.\n' >&2
    exit 2
}
export PACK= REBUILD=
source "$AI_TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export PYTHONPATH="$AI_TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}" VECLIB_MAXIMUM_THREADS=1
printf 'Source commit: '
git rev-parse HEAD
printf 'Phase: %s\nCompact source: %s\n' "$AI_PHASE" "$AI_COMPACT"
python -B -c 'import torch; assert torch.cuda.is_available(), "A CUDA GPU is required"; print("Torch", torch.__version__, "CUDA", torch.version.cuda, "GPU", torch.cuda.get_device_name(0))'
# The Python reader inventories explicit allowlisted season directories only;
# it stages no 2026/test paths. The diagnostic branch opens TRAIN payloads only.
python -B -m ai_experiments "${AI_ARGS[@]}" --device cuda \
    --compact "$AI_COMPACT" --out-dir "$AI_OUTPUT" --scratch "$AI_SCRATCH"
