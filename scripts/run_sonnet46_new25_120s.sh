#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .venv/bin/activate
source "$HOME/.cargo/env"
export PATH="$HOME/.local/bin:$PATH"
export USE_TORCH=0 USE_TF=0 TOKENIZERS_PARALLELISM=false
export VB_VERUS_BIN="${VB_VERUS_BIN:-$PWD/.local-tools/verusbench/verus/verus}"
export VB_Z3_BIN="${VB_Z3_BIN:-$PWD/.local-tools/verusbench/verus/z3}"
export VB_LYNETTE_BIN="${VB_LYNETTE_BIN:-$PWD/.local-tools/verusbench/lynette}"
python -u -m scripts.run_sonnet46_new25_120s "$@"
