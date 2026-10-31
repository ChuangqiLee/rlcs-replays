#!/bin/bash
#SBATCH -J env_check
#SBATCH -p amperenodes
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=48G
#SBATCH -t 01:00:00
#SBATCH -o logs/env_check-%j.out
t0=$(date +%s); source $HOME/workspace/rlcs-replays/tactics/slurm/env.sh; echo "env ready in $(( $(date +%s)-t0 ))s"
python - <<'P'
import glob, json, torch, numpy, pandas, pyarrow, pyarrow.parquet as pq
print("versions torch", torch.__version__, "numpy", numpy.__version__, "pandas", pandas.__version__, "pyarrow", pyarrow.__version__)
try:
    import torch_geometric; print("pyg", torch_geometric.__version__)
    import torch_scatter; print("torch_scatter ok")
except Exception as e: print("pyg issue", e)
base = "/home/c.li16@students.uu.nl/workspace/rlcs-replays/data/frames/fps30"
f = sorted(p for p in glob.glob(f"{base}/*/*.parquet") if not p.endswith(".index.parquet"))[0]
pf = pq.ParquetFile(f); print("file", f, "row_groups", pf.num_row_groups, "cols", pf.schema_arrow.names.__len__())
t = pf.read_row_group(0).to_pandas(); print("rg0 shape", t.shape)
x = torch.tensor(t.select_dtypes("float32").to_numpy(), device="cuda"); print("on GPU", x.shape, x.device, torch.nanmean(x).item())
P
