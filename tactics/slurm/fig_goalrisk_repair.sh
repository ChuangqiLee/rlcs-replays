#!/bin/bash
#SBATCH --job-name=risk-repair
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=24G
#SBATCH --time=01:30:00
#SBATCH --output=logs/risk-repair-%j.log
#SBATCH --error=logs/risk-repair-%j.log
# Re-pair the two team views of the stored 2025 goal-risk predictions (results/ai_risk/41119498) and re-extract the
# goal-risk figure data with 2,000 whole-series bootstrap draws. Nothing is refit; riskrun.py is not modified.
# Usage: sbatch slurm/fig_goalrisk_repair.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
TACT=${TACT:-$HOME/workspace/rlcs-replays/tactics}
cd "$SLURM_SUBMIT_DIR"
source "$TACT/slurm/env.sh"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN=41119498
OUT="$TACT/results/ai_risk/${RUN}-paired"
DATASET="$TACT/artifacts/ai_risk/medium-h60"
cd "$TACT/paper_r28/figscripts"
python -B repair_risk_pairing.py --run "$TACT/results/ai_risk/$RUN" --dataset "$DATASET" --out "$OUT" --draws 2000
python -B fig_goalrisk.py --extract "$OUT" --dataset "$DATASET" --draws 2000 --extract-only
ls -l "$OUT" data/fig_goalrisk_*.csv data/fig_goalrisk_provenance.json
