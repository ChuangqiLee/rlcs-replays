#!/bin/bash
#SBATCH --job-name=rq4-habits
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=03:00:00
#SBATCH --output=logs/rq4-habits-%j.out
#SBATCH --error=logs/rq4-habits-%j.err

# Run from the integrated repository root. Create logs/ before submission.
# Resource ceilings are planning choices; see docs/RQ4_habits_implementation.md
# and results/rq4_habits_validation.json for the computed timing estimate.
set -euo pipefail
TASK_ROOT="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$TASK_ROOT"
mkdir -p logs
if [[ ! -f slurm/env.sh ]]; then
    echo 'Required project environment is missing: slurm/env.sh' >&2
    exit 1
fi
# The existing environment may reference unset module variables.
set +u
source slurm/env.sh
set -u
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$TASK_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1
ARGS=()
if [[ -n "${RQ4_COMPACT:-}" ]]; then
    ARGS+=(--compact "$RQ4_COMPACT")
fi
if [[ -n "${RQ4_MAX_REPLAYS:-}" ]]; then
    ARGS+=(--max-replays "$RQ4_MAX_REPLAYS")
fi
date -u
python -B src/tests/test_habit_stability.py
# Bash 4.2 with nounset requires this guard even for declared empty arrays.
python -B -m tactics_code.habit_stability \
    --output-dir "${RQ4_OUTPUT_DIR:-results/rq4_habits}" ${ARGS[@]+"${ARGS[@]}"}
date -u
