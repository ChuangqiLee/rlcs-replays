#!/bin/bash
#SBATCH --job-name=rlcs-p3-full
#SBATCH --partition=amperenodes
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=3-00:00:00
#SBATCH --output=logs/p3-full-%j.log
#SBATCH --error=logs/p3-full-%j.log
set -eo pipefail  # no -u: bash 4.2 treats empty arrays as unbound
source "$HOME/workspace/rlcs-replays/tactics/slurm/env.sh"
export P3_MODE=full
exec bash "$HOME/workspace/rlcs-replays/tactics/slurm/p3_pipeline.sh"
