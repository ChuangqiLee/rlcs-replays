#!/bin/bash
#SBATCH --job-name=posthoc-sens
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/posthoc-sens-%j.out
set -eo pipefail
cd "$SLURM_SUBMIT_DIR"
set +u; unset PACK; source slurm/env.sh; set -u
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}" OMP_NUM_THREADS=1
A=$HOME/workspace/rlcs-replays
KO=$(dirname "$(ls -d $A/analysis/*/artifacts/p6_kickoff/val/kickoff_units.parquet | grep 41105020 | head -1)")/..
python -B -m tactics_code.posthoc_sens --p5-artifacts "$A/tactics/artifacts/p5-latency-41105041" \
  --kickoff-artifacts "$KO" --out "$A/analysis/posthoc-sens-$SLURM_JOB_ID/posthoc_sens.json"
