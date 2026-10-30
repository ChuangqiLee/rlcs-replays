#!/bin/bash
# Build the project environment from scratch. Usage: bash setup_env.sh
#
# The home filesystem (GPFS) is very slow at creating many small files, so the heavy
# packages (numpy, pandas, scipy, requests) come from the cluster module SciPy-bundle;
# the venv only adds the few packages in requirements.txt. --without-pip avoids writing
# a private copy of pip; the module's pip installs into the venv instead.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULES="SciPy-bundle/2023.11-gfbf-2023b"

# Lmod's module function is not inherited by non-interactive shells; the system
# profile scripts are not written for `set -eu`, so relax it while sourcing them.
if ! type module >/dev/null 2>&1; then
    set +eu
    source /etc/profile
    set -eu
fi
module load $MODULES

cd "$PROJECT_DIR"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv --system-site-packages --without-pip .venv
fi
source .venv/bin/activate
python -m pip install --only-binary=:all: -r requirements.txt

python -c "import subtr_actor, pyarrow, pandas, numpy; print('environment OK:', 'pyarrow', pyarrow.__version__, 'pandas', pandas.__version__, 'numpy', numpy.__version__)"
