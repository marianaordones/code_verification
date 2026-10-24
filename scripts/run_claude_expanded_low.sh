#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# != 1 || ! "$1" =~ ^(prepare|run|compare)$ ]]; then
    echo "Usage: bash scripts/run_claude_expanded_low.sh prepare|run|compare" >&2
    exit 2
fi
source .venv/bin/activate
source "$HOME/.cargo/env"
export USE_TORCH=0 USE_TF=0 TOKENIZERS_PARALLELISM=false
export VERUS_BIN="$PWD/.local-tools/verus/verus"
export Z3_BIN="$PWD/.local-tools/verus/z3"
export VERUS_Z3_PATH="$Z3_BIN"
python -u -m solver_needs_study "$1" \
    --study results/claude-local-expanded60-low-v2 \
    --tasks 60 --selection configs/solver-needs-claude-expanded60.json \
    --config configs/solver-needs-claude-low.json
