#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .venv/bin/activate
source "$HOME/.cargo/env"
export PATH="$HOME/.local/bin:$PATH"
export USE_TORCH=0 USE_TF=0 TOKENIZERS_PARALLELISM=false
export VERUS_BIN="$PWD/.local-tools/verus/verus"
export Z3_BIN="$PWD/.local-tools/verus/z3"
export VERUS_Z3_PATH="$Z3_BIN"
python -u -m missing_opus48 "${1:?Use prepare, run or compare}" \
    --study "${2:-results/missing-opus48-low-shared20-50x3-v1}"
