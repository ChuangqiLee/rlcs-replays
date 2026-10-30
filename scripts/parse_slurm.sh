#!/bin/bash
# Parse all downloaded replays on a compute node. Re-submit any time; finished replays are skipped.
# Usage: sbatch scripts/parse_slurm.sh
#SBATCH --job-name=rlcs-parse
#SBATCH --partition=short
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --output=logs/parse-%j.log

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}"
# Local shard files of an earlier, cancelled job on this node (run only one parse job at a time).
rm -rf "${TMPDIR:-/tmp}"/rlcs-parse-* /local/rlcs-parse-* /tmp/rlcs-parse-* 2>/dev/null || true
source env.sh
python scripts/parse_replays.py --workers "${SLURM_CPUS_PER_TASK:-32}" --fps 30
