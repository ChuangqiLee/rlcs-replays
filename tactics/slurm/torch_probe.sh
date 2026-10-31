#!/bin/bash
#SBATCH -J torch_probe
#SBATCH -p amperenodes
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH -t 00:40:00
#SBATCH -o logs/torch_probe-%j.out
# Builds a node-local conda env (glibc 2.17 compatible torch 2.5.1+cu121, manylinux2014 wheels)
module reset >/dev/null 2>&1; module load Miniforge3/24.3.0-0
D=${TMPDIR:-/local/$USER/$SLURM_JOB_ID}/dlenv; mkdir -p $D
export PIP_CACHE_DIR=$D/pipcache CONDA_PKGS_DIRS=$D/pkgs
conda create -q -y -p $D/env python=3.11 pip >/dev/null; export PATH=$D/env/bin:$PATH; which python
python -m pip install -q torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121 2>&1 | tail -3
python -m pip install -q pyarrow pandas 2>&1 | tail -2
cat > $D/t.py <<'P'
import sys, time, torch
print("PY", sys.version.split()[0], "TORCH", torch.__version__, "CUDA", torch.version.cuda, "cuDNN", torch.backends.cudnn.version())
print("avail", torch.cuda.is_available(), torch.cuda.get_device_name(0), round(torch.cuda.get_device_properties(0).total_memory/2**30,1), "GiB")
x = torch.randn(8192, 8192, device="cuda", dtype=torch.bfloat16); torch.cuda.synchronize(); t=time.time()
for _ in range(50): y = x @ x
torch.cuda.synchronize(); dt=time.time()-t; print("bf16 TFLOPS", round(50*2*8192**3/dt/1e12,1))
P
python $D/t.py
du -sh $D/env
