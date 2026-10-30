# Activate the project environment. Usage: source env.sh
# Must be sourced (not executed) so the module and venv apply to the current shell.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULES="SciPy-bundle/2023.11-gfbf-2023b"

module load $MODULES || { echo "module load $MODULES failed" >&2; return 1; }

if [ ! -x "$PROJECT_DIR/.venv/bin/python" ]; then
    echo "No .venv found; run: bash $PROJECT_DIR/setup_env.sh" >&2
    return 1
fi
source "$PROJECT_DIR/.venv/bin/activate"
