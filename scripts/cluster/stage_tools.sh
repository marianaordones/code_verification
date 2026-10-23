#!/usr/bin/env bash
# Source after runtime initialization, once per job. Persistent archives stay on
# shared storage; the complete Verus distribution executes from local scratch.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Source stage_tools.sh from the job." >&2
    exit 2
fi
source scripts/cluster/native_workspace.sh
exec 8>.cluster/tools.lock
flock -s 8
if [[ -f .cluster/tools-native.json && -f .cluster/tools-native.tar.gz ]]; then
    python - <<'PY'
import hashlib,json,pathlib
manifest=json.loads(pathlib.Path(".cluster/tools-native.json").read_text())
assert manifest["complete"], "Incomplete tool bundle"
assert hashlib.sha256(pathlib.Path(".cluster/tools-native.tar.gz").read_bytes()).hexdigest()==manifest["sha256"], "Tool bundle hash mismatch"
PY
    native_workspace 2
    tar -xzf .cluster/tools-native.tar.gz -C "$NATIVE_WORKSPACE"
    export VERUS_BIN="$NATIVE_WORKSPACE/verus/verus"
    export Z3_BIN="$NATIVE_WORKSPACE/verus/z3"
    export LYNETTE_BIN="$NATIVE_WORKSPACE/lynette"
elif [[ -n "${VERUS_BIN:-}" && -n "${Z3_BIN:-}" && -n "${LYNETTE_BIN:-}" ]]; then
    echo "Using explicitly supplied tool paths (must support native execution)."
else
    echo "Run the updated prepare.slurm first; native tool bundle is missing." >&2
    return 34
fi
"$VERUS_BIN" --version
"$Z3_BIN" --version
"$LYNETTE_BIN" --help >/dev/null
export VERUS_Z3_PATH="$Z3_BIN"
flock -u 8
exec 8>&-
