# Source inside a SLURM job: sets up the DL env on node-local disk.
# Uses packed tarball tactics/envs/dlenv.tar.gz if present, else builds it (and packs with PACK=1).
module reset >/dev/null 2>&1; module load Miniforge3/24.3.0-0
TACT=${TACT:-$HOME/workspace/rlcs-replays/tactics}
D=${TMPDIR:-/local/$USER}/dlenv-${SLURM_JOB_ID:-x}; mkdir -p $D  # job-unique: shared /scratch/local races
export PIP_CACHE_DIR=$D/pipcache CONDA_PKGS_DIRS=$D/pkgs
TAR=$TACT/envs/dlenv.tar.gz
if [ -f "$TAR" ] && [ -z "${REBUILD:-}" ]; then
  mkdir -p $D/env && tar -xzf $TAR -C $D/env && $D/env/bin/conda-unpack
else
  conda create -q -y -p $D/env -c conda-forge python=3.11 numpy pandas pyarrow scipy scikit-learn conda-pack >/dev/null
  $D/env/bin/python -m pip install -q torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
  $D/env/bin/python -m pip install -q torch_geometric
  $D/env/bin/python -m pip install -q pyg_lib torch_scatter -f https://data.pyg.org/whl/torch-2.5.0+cu121.html || echo "pyg ext failed (optional)"
  if [ -n "${PACK:-}" ]; then mkdir -p $TACT/envs; $D/env/bin/conda-pack -q -p $D/env -o $D/dlenv.tar.gz --ignore-missing-files && cp $D/dlenv.tar.gz $TAR; fi
fi
export PATH=$D/env/bin:$PATH
python -c "import matplotlib, statsmodels" 2>/dev/null || conda install -y -q -p $D/env -c conda-forge matplotlib-base statsmodels >/dev/null
