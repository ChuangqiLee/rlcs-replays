#!/bin/bash
#SBATCH --job-name=ai-cache
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=03:00:00
#SBATCH --output=logs/ai-cache-%j.log
#SBATCH --error=logs/ai-cache-%j.log
# Build the reusable AI window cache (float16 chunks, one per compact shard)
# from an allowlisted compact source. CPU only. Usage:
#   AI_COMPACT=<compact dir> AI_CACHE_NAME=<name> sbatch slurm/ai_cache.sh
set -eo pipefail
: "${SLURM_JOB_ID:?Refusing to run outside SLURM; use sbatch}"
: "${SLURM_SUBMIT_DIR:?SLURM must supply the submission directory}"
: "${TMPDIR:?SLURM must supply node-local scratch}"
: "${AI_COMPACT:?Set AI_COMPACT to the approved compact source}"
: "${AI_CACHE_NAME:?Set AI_CACHE_NAME}"
AI_CAP="${AI_CAP:-64}"
AI_LIMIT="${AI_LIMIT:-0}"
case "$AI_COMPACT" in
    *2026*|*/test|*/test/*) printf '2026/test compact paths are forbidden.\n' >&2; exit 2 ;;
esac
cd "$SLURM_SUBMIT_DIR"
export TACT="$PWD"
test -f "$TACT/envs/dlenv.tar.gz" || { printf 'envs/dlenv.tar.gz required\n' >&2; exit 2; }
export PACK= REBUILD=
source "$TACT/slurm/env.sh"
set -u
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export PYTHONPATH="$TACT/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
OUT="$TACT/artifacts/ai_cache/$AI_CACHE_NAME"
if [ -e "$OUT" ]; then printf 'Cache exists: %s\n' "$OUT" >&2; exit 2; fi
mkdir -p "$TACT/artifacts/ai_cache"
printf 'Source commit: '; git rev-parse HEAD
printf 'Compact: %s\nCache: %s\nCap: %s\n' "$AI_COMPACT" "$OUT" "$AI_CAP"
python -B -m ai_experiments.cache --compact "$AI_COMPACT" --out "$OUT" \
    --cap "$AI_CAP" --workers "$SLURM_CPUS_PER_TASK" --limit "$AI_LIMIT" ${AI_CACHE_FLAGS:-}
ls -la "$OUT" | head -40 || true
du -sh "$OUT"
