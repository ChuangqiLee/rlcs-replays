#!/bin/bash
#SBATCH --job-name=rlcs-p3-small
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --output=logs/p3-small-%j.log
#SBATCH --error=logs/p3-small-%j.log
set -eo pipefail  # no -u: bash 4.2 treats empty arrays as unbound
source "$HOME/workspace/rlcs-replays/tactics/slurm/env.sh"
export P3_MODE=small
exec bash "$HOME/workspace/rlcs-replays/tactics/slurm/p3_pipeline.sh"
