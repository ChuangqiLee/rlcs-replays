#!/bin/bash
#SBATCH --job-name=fig-footprints
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:50:00
#SBATCH --output=logs/fig-footprints-%j.log
#SBATCH --error=logs/fig-footprints-%j.log
# 2025 live-frame position histograms of the three profiled players for the habit figure (reads the
# rlcs-2025 compact shards; no statistics are recomputed). Usage: sbatch slurm/fig_footprints.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
TACT=${TACT:-$HOME/workspace/rlcs-replays/tactics}
cd "$SLURM_SUBMIT_DIR"
source "$TACT/slurm/env.sh"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
python -B paper_r28/figscripts/extract_scenes.py footprints
