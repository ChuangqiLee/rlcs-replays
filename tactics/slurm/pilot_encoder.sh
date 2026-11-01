#!/bin/bash
#SBATCH --job-name=pilot-encoder
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/pilot-encoder-%j.log
#SBATCH --error=logs/pilot-encoder-%j.log
# Run manually from the repository; never run this script on a login host.
# Four hours is 1.6x the 9,000-second (2.5 GPU-hour) operational cap.
# Training is separately capped at 6,300 seconds, reserving preprocessing/inference.
# See paper/PILOT_ENCODER.md and docs/PILOT_ENCODER_impl.md for fixed settings.
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; submit using sbatch}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
# Both Python invocations inherit the whole-job clock, including environment
# setup and staging, so their remaining operational budget cannot reset.
export PILOT_START_EPOCH="$(date +%s)"
VARIANT="${VARIANT:-v1}"
PILOT_MODULE=pilot_encoder
case "$VARIANT" in
    v1|v2) ;;
    v3|v4) PILOT_MODULE=pilot_encoder.run_adapted ;;
    *) printf 'VARIANT must be v1, v2, v3 or v4, got %s\n' "$VARIANT" >&2; exit 2 ;;
esac
PILOT_TACT="${PILOT_TACT:-$SLURM_SUBMIT_DIR}"
cd "$PILOT_TACT"
PILOT_TACT="$PWD"
export TACT="$PILOT_TACT"
source "$PILOT_TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Preserve module-provided dependency paths while exposing the local packages.
export PYTHONPATH="$PILOT_TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"
export VECLIB_MAXIMUM_THREADS=1
PILOT_SOURCE="${PILOT_COMPACT:-$PILOT_TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact}"
PILOT_SCRATCH="$TMPDIR/pilot-encoder-$SLURM_JOB_ID-$VARIANT"
mkdir "$PILOT_SCRATCH"
mkdir -p "$PILOT_TACT/results"
printf 'Source commit: '
git rev-parse HEAD
printf 'Variant: %s\nCompact source: %s\n' "$VARIANT" "$PILOT_SOURCE"
python -B -c 'import torch; assert torch.cuda.is_available(), "A CUDA GPU is required"; print("Torch", torch.__version__, "CUDA", torch.version.cuda, "GPU", torch.cuda.get_device_name(0))'
# The pilot wrapper reuses RQ4 inventory/staging and explicit season assertions.
# Only prevalidated allowed-season NPZ/parquet files, extraction.json and any
# optional decode-exclusion metadata copy;
# no recursive directory copy, raw replay access, or 2026 discovery occurs.
PILOT_EXIT_STATUS=0
python -B -m "$PILOT_MODULE" \
    --variant "$VARIANT" --compact "$PILOT_SOURCE" \
    --stage-to "$PILOT_SCRATCH/compact" \
    --out "$PILOT_SCRATCH/pilot_encoder_${VARIANT}.json" || PILOT_EXIT_STATUS=$?
if [ "$PILOT_EXIT_STATUS" -eq 0 ]; then
    python -B -m "$PILOT_MODULE" \
        --variant "$VARIANT" --device cuda \
        --compact "$PILOT_SCRATCH/compact" --source-compact "$PILOT_SOURCE" \
        --checkpoint-dir "$PILOT_SCRATCH/checkpoints" \
        --out "$PILOT_SCRATCH/pilot_encoder_${VARIANT}.json" || PILOT_EXIT_STATUS=$?
fi
# Preserve structured failure/budget reports as well as successful results.
# A staging failure cannot launch training; its report is copied below.
if [ -f "$PILOT_SCRATCH/pilot_encoder_${VARIANT}.json" ]; then
    cp "$PILOT_SCRATCH/pilot_encoder_${VARIANT}.json" \
        "$PILOT_TACT/results/pilot_encoder_${VARIANT}.json"
fi
exit "$PILOT_EXIT_STATUS"
