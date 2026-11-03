#!/bin/bash
# Invoke manually on the cluster from the extracted repository. This script is
# deliberately not invoked by local development, tests or the deploy packager.
set -euo pipefail
: "${AI_COMPACT:?Set AI_COMPACT to the approved compact source before submission}"
AI_TACT="${AI_TACT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$AI_TACT"
export AI_TACT AI_COMPACT
command -v sbatch >/dev/null || { printf 'sbatch is required.\n' >&2; exit 2; }
mkdir -p logs
# Refuse the common explicit holdout mistakes before asking Slurm for resources.
case "$AI_COMPACT" in
    *2026*|*/test|*/test/*) printf '2026/test compact paths are forbidden.\n' >&2; exit 2 ;;
esac
# sbatch --parsable may append a cluster name separated by a semicolon.
AI_SMOKE_REPLY="$(sbatch --parsable slurm/ai_smoke.sh)"
AI_SMOKE_JOB="${AI_SMOKE_REPLY%%;*}"
printf 'Synthetic smoke job: %s\n' "$AI_SMOKE_JOB"
AI_DIAG_REPLY="$(AI_PHASE=diagnose sbatch --parsable --dependency="afterok:$AI_SMOKE_JOB" slurm/ai_full.sh)"
AI_DIAG_JOB="${AI_DIAG_REPLY%%;*}"
printf 'Train-only diagnostic gate job: %s (afterok:%s)\n' "$AI_DIAG_JOB" "$AI_SMOKE_JOB"
AI_FULL_REPLY="$(AI_PHASE=full sbatch --parsable --dependency="afterok:$AI_DIAG_JOB" --array=0-59%4 slurm/ai_full.sh)"
AI_FULL_JOB="${AI_FULL_REPLY%%;*}"
printf 'Full experiment array job: %s (afterok:%s; 60 tasks, at most 4 concurrent)\n' "$AI_FULL_JOB" "$AI_DIAG_JOB"
for AI_TASK in {0..59}; do
    printf 'Full task ID: %s_%s\n' "$AI_FULL_JOB" "$AI_TASK"
done
printf 'Submitted 61 full jobs (1 diagnostic + 60 experiments), plus 1 synthetic smoke.\n'
