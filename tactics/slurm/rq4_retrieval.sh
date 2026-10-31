#!/bin/bash
#SBATCH --job-name=rq4-retrieval
#SBATCH --partition=amd-hdr100
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=00:25:00
#SBATCH --output=logs/rq4-retrieval-%j.log
#SBATCH --error=logs/rq4-retrieval-%j.log
# Measured smoke: 30/6000 replays, 3.707 s features + 4.809 s inventory.
# Full-size inference benchmark: 112 players, 1007 queries, both analyses,
# 2000 permutations + 2000 bootstraps: 3.154 s. Linear feature projection:
# 3.707*6000/30 + 4.809 + 3.154 = 749 s; allow ~60 s to stage 6.26 GB.
# Expected ~13.5 minutes; 25-minute limit is ~1.85x. Full reader decompresses
# each shard once; smoke slice seeks are conservative. See docs/RQ4_retrieval.md.
# CPU only. Never automatically submit this script.
set -eo pipefail
: "${SLURM_JOB_ID:?Submit using sbatch}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
RQ4_TACT="${RQ4_TACT:-$HOME/workspace/rlcs-replays/tactics}"
cd "$RQ4_TACT/.."
source env.sh
cd "$RQ4_TACT"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Keep module-provided dependency paths from the project's env.sh.
export PYTHONPATH="$RQ4_TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
RQ4_SOURCE="${RQ4_COMPACT:-$RQ4_TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact}"
RQ4_SCRATCH="$TMPDIR/rq4-retrieval-$SLURM_JOB_ID"
mkdir "$RQ4_SCRATCH"
mkdir -p "$RQ4_TACT/results"
printf 'Source commit: '
git rev-parse HEAD
printf 'Compact source: %s\n' "$RQ4_SOURCE"
# The staging helper validates metadata and guards symlinks before copying.
# Only explicit allowlisted NPZ/parquet files and extraction.json are copied;
# it never recursively copies directories or discovers held-out files.
python -B -m tactics_code.style_retrieval \
    --compact "$RQ4_SOURCE" --stage-to "$RQ4_SCRATCH/compact"
python -B -m tactics_code.style_retrieval \
    --compact "$RQ4_SCRATCH/compact" \
    --out "$RQ4_SCRATCH/rq4_retrieval.json" \
    --permutations 2000 --bootstrap 2000 --seed 42
cp "$RQ4_SCRATCH/rq4_retrieval.json" "$RQ4_TACT/results/rq4_retrieval.json"
