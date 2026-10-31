#!/bin/bash
#SBATCH --job-name=rlcs-cases
#SBATCH --partition=amd-hdr100
#SBATCH --cpus-per-task=4
#SBATCH --ntasks=1
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH --output=logs/cases-%j.log
#SBATCH --error=logs/cases-%j.log
# CPU only. Descriptive case extraction, rlcs-2025 val only (script guards 2026).
# Runtime unmeasured on real data: three native passes over val shards; 3 h cap.
set -eo pipefail
: "${SLURM_JOB_ID:?sbatch only}"
export TACT="${TACT:-$HOME/workspace/rlcs-replays/tactics}"
cd "$TACT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH="$TACT/src"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
unset PACK
source "$TACT/slurm/env.sh"
set -u
OUT="$TACT/artifacts/cases-$SLURM_JOB_ID"
mkdir -p "$OUT"
git rev-parse HEAD > "$OUT/source_commit.txt"
python scripts/cases/extract_cases.py --repo "$TACT" \
  --compact "$TACT/artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact" \
  --data-root "$HOME/workspace/rlcs-replays/data" \
  --state-map "$TACT/state_map_rlcs.json" --tercile empirical --out "$OUT"
python scripts/cases/make_fig_cases.py --repo "$TACT" --cases "$OUT/cases.parquet" --out "$OUT/figures"
