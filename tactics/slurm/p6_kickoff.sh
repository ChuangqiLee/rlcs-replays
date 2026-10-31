#!/usr/bin/env bash
#SBATCH --job-name=p6-kickoff
#SBATCH --partition=amd-hdr100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=logs/p6-kickoff-%j.log
#SBATCH --error=logs/p6-kickoff-%j.log

# Prepared job recipe only; this file does not submit jobs or transfer files.
# Mac synthetic CPU projection: 1.24 minutes; artifacts/timing.json.
# Excludes real replay I/O and AMD calibration; walltime above is only a ceiling.
# Runtime calibration: run with P6_PILOT_SERIES first and inspect result.timing.
set -euo pipefail
: "${P6_REPO:?Set P6_REPO to the integrated repository}"
: "${P6_COMPACT:?Set P6_COMPACT to the decoded compact root}"
: "${P6_DATA_ROOT:?Set P6_DATA_ROOT to the native data root}"
: "${P6_STATE_MAP:?Set P6_STATE_MAP to the reviewed state map JSON}"
: "${P6_OUTPUT:?Set P6_OUTPUT to a separate writable analysis root}"
P6_PYTHON="${P6_PYTHON:-python}"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${P6_REPO}/src${PYTHONPATH:+:${PYTHONPATH}}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
args=(--compact "$P6_COMPACT" --data-root "$P6_DATA_ROOT" --state-map "$P6_STATE_MAP" --output "$P6_OUTPUT")
if [[ -n "${P6_THRESHOLDS:-}" ]]; then args+=(--thresholds "$P6_THRESHOLDS"); fi
if [[ -n "${P6_PILOT_SERIES:-}" ]]; then args+=(--pilot-series "$P6_PILOT_SERIES"); fi
if [[ -n "${P6_BOOST_FULL_SCALE:-}" ]]; then args+=(--boost-full-scale "$P6_BOOST_FULL_SCALE"); fi
cd "$P6_REPO"
set +u; unset PACK; source "$P6_REPO/slurm/env.sh"; set -u
exec "$P6_PYTHON" -B -m tactics_code.kickoff "${args[@]}"
