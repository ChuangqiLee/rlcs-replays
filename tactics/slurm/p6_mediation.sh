#!/usr/bin/env bash
# descriptive decomposition, not causal mediation
#SBATCH --job-name=p6-mediation
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=02:40:00
#SBATCH --output=logs/p6_mediation-%j.out
#SBATCH --error=logs/p6_mediation-%j.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# logs/ must exist before submitting; Slurm opens its logs before this script.
mkdir -p logs
set +u; unset PACK; source slurm/env.sh; set -u
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

: "${P6_COMPACT:?Set P6_COMPACT to the local compact directory}"
: "${P6_DATA_ROOT:?Set P6_DATA_ROOT to the local native replay data directory}"
: "${P6_STATE_MAP:?Set P6_STATE_MAP to the local state-map JSON file}"
P6_PYTHON="${P6_PYTHON:-python}"
P6_ARTIFACTS="${P6_ARTIFACTS:-$PWD/artifacts/p6-mediation-${SLURM_JOB_ID:-local}}"
P6_OUTPUT="${P6_OUTPUT:-$PWD/results/boost_mediation.json}"
P6_SCRATCH="${P6_SCRATCH:-$P6_ARTIFACTS/scratch}"
mkdir -p "$P6_ARTIFACTS" "$P6_SCRATCH"

# Timing budget: artifacts/runtime_estimate.json and implementation note.
# Whole-series inference is serial; shard extraction uses allocated CPUs.
"$P6_PYTHON" -m tactics_code.boost_mediation \
  --compact "$P6_COMPACT" --data-root "$P6_DATA_ROOT" \
  --state-map "$P6_STATE_MAP" --artifacts "$P6_ARTIFACTS" \
  --scratch "$P6_SCRATCH" --out "$P6_OUTPUT" \
  --workers "${SLURM_CPUS_PER_TASK:-1}"
