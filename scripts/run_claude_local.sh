#!/usr/bin/env bash
# Run under WSL/Linux. Does not install dependencies or use Slurm/GPU.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "Usage: bash scripts/run_claude_local.sh prepare|run|compare STUDY_DIR [TASKS]" >&2
    exit 2
fi
source .venv/bin/activate
source "$HOME/.cargo/env"
export USE_TORCH=0 USE_TF=0 TOKENIZERS_PARALLELISM=false
export VERUS_BIN="$PWD/.local-tools/verus/verus"
export Z3_BIN="$PWD/.local-tools/verus/z3"
export VERUS_Z3_PATH="$Z3_BIN"
python -m solver_needs_study "$1" --study "$2" --tasks "${3:-1}" \
    --config configs/solver-needs-claude-local.json
