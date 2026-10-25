#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -lt 1 || $# -gt 2 || ! "$1" =~ ^(prepare|run|compare)$ ]]; then
    echo "Usage: bash scripts/run_verusbench_claude.sh prepare|run|compare [STUDY_DIR]" >&2
    exit 2
fi
source .venv/bin/activate
source "$HOME/.cargo/env"
export PATH="$HOME/.local/bin:$PATH"
export USE_TORCH=0 USE_TF=0 TOKENIZERS_PARALLELISM=false
export VB_VERUS_BIN="${VB_VERUS_BIN:-$PWD/.local-tools/verusbench/verus/verus}"
export VB_Z3_BIN="${VB_Z3_BIN:-$PWD/.local-tools/verusbench/verus/z3}"
export VB_LYNETTE_BIN="${VB_LYNETTE_BIN:-$PWD/.local-tools/verusbench/lynette}"
extra=()
if [[ "$1" == prepare && -n "${VB_SOURCE_STUDY:-}" ]]; then
    extra+=(--from-study "$VB_SOURCE_STUDY")
fi
python -u -m verusbench_study "$1" --study "${2:-results/verusbench-claude5-low-v2}" \
    --config "${VB_CLAUDE_CONFIG:-configs/verusbench-claude5.json}" "${extra[@]}"
