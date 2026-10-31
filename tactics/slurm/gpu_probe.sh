#!/bin/bash
#SBATCH -J gpu_probe
#SBATCH -p amperenodes
#SBATCH --gres=gpu:1
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH -t 00:20:00
#SBATCH -o logs/gpu_probe-%j.out
set -x
hostname; ldd --version | head -1; cat /etc/redhat-release
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
nvidia-smi | head -5
echo TMPDIR=$TMPDIR; df -h /local "$TMPDIR" 2>/dev/null
module -t avail 2>&1 | grep -iE "torch|cuda" 
for m in $(module -t avail 2>&1 | grep -iE "torch" ); do
  echo "=== $m"; ( module purge; module load $m 2>&1; python -c "import torch,sys;print(sys.version.split()[0],torch.__version__,torch.version.cuda,torch.cuda.is_available(),torch.cuda.get_device_name(0));x=torch.randn(4096,4096,device='cuda');print((x@x).sum().item())" 2>&1 | tail -3 )
done
# fallback: pip torch into node-local disk
D=${TMPDIR:-/local/$USER/$SLURM_JOB_ID}; mkdir -p $D
module purge; module load Anaconda3/2023.07-2 2>/dev/null || module load SciPy-bundle/2023.11-gfbf-2023b
python -m venv $D/venv && source $D/venv/bin/activate && pip -q install --cache-dir $D/pipcache torch --index-url https://download.pytorch.org/whl/cu121 2>&1 | tail -2
python -c "import torch,sys;print('PIPTORCH',sys.version.split()[0],torch.__version__,torch.version.cuda,torch.cuda.is_available(),torch.cuda.get_device_name(0));x=torch.randn(4096,4096,device='cuda');print((x@x).sum().item())" 2>&1 | tail -3
