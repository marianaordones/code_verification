#!/usr/bin/env bash
# Reuse the existing native tool builder locally; does not submit Slurm jobs.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .venv/bin/activate
source "$HOME/.cargo/env"
export CARGO_BUILD_JOBS=1
rustup toolchain install stable --profile minimal --no-self-update
unset VERUS_BIN Z3_BIN LYNETTE_BIN
SLURM_SUBMIT_DIR="$PWD" bash scripts/cluster/setup_tools.sh
python - <<'PY'
from pathlib import Path
from baseline.storage import read_json, digest
archive = Path('.cluster/tools-native.tar.gz')
receipt = read_json('.cluster/tools-native.json')
assert receipt['complete'] and digest(archive.read_bytes()) == receipt['sha256']
PY
destination=.local-tools/verusbench
if [[ -e "$destination" ]]; then
    echo "Destination already exists; inspect it rather than overwriting tool binaries." >&2
    exit 2
fi
mkdir -p "$destination"
tar -xzf .cluster/tools-native.tar.gz -C "$destination"
"$destination/verus/verus" --version
"$destination/verus/z3" --version
"$destination/lynette" --help >/dev/null
