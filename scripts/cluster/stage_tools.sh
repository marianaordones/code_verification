#!/usr/bin/env bash
# Source after runtime initialization, once per job. Persistent archives stay on
# shared storage; the complete Verus distribution executes from local scratch.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Source stage_tools.sh from the job." >&2
    exit 2
fi
source scripts/cluster/native_workspace.sh
tools_bundle_dir="${VERUSBENCH_TOOLS_DIR:-.cluster}"
# A fresh Git clone does not include .cluster; reuse the existing sibling cache.
if [[ -z "${VERUSBENCH_TOOLS_DIR:-}" && ! -f "$tools_bundle_dir/tools-native.json" ]]; then
    sibling_cache="$(dirname -- "$PROJECT_ROOT")/code_verification/.cluster"
    if [[ -f "$sibling_cache/tools-native.json" && -f "$sibling_cache/tools-native.tar.gz" ]]; then
        tools_bundle_dir="$sibling_cache"
    fi
fi
if [[ -f "$tools_bundle_dir/tools-native.json" && -f "$tools_bundle_dir/tools-native.tar.gz" ]]; then
    echo "VerusBench native bundle: $tools_bundle_dir"
    exec 8>"$tools_bundle_dir/tools.lock"
    flock -s 8
    python - "$tools_bundle_dir" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1])
manifest=json.loads((root / "tools-native.json").read_text())
assert manifest["complete"], "Incomplete tool bundle"
assert hashlib.sha256((root / "tools-native.tar.gz").read_bytes()).hexdigest()==manifest["sha256"], "Tool bundle hash mismatch"
PY
    native_workspace 2
    tar -xzf "$tools_bundle_dir/tools-native.tar.gz" -C "$NATIVE_WORKSPACE"
    export VERUS_BIN="$NATIVE_WORKSPACE/verus/verus"
    export Z3_BIN="$NATIVE_WORKSPACE/verus/z3"
    export LYNETTE_BIN="$NATIVE_WORKSPACE/lynette"
elif [[ -n "${VERUS_BIN:-}" && -n "${Z3_BIN:-}" && -n "${LYNETTE_BIN:-}" ]]; then
    echo "Using explicitly supplied tool paths (must support native execution)."
else
    echo "VerusBench native bundle missing in $tools_bundle_dir and the old sibling repository." >&2
    echo "Set VERUSBENCH_TOOLS_DIR to the existing .cluster directory (tools-native.json and tools-native.tar.gz)." >&2
    return 34
fi
"$VERUS_BIN" --version
"$Z3_BIN" --version
"$LYNETTE_BIN" --help >/dev/null
export VERUS_Z3_PATH="$Z3_BIN"
if [[ -f "$tools_bundle_dir/tools-native.json" && -f "$tools_bundle_dir/tools-native.tar.gz" ]]; then
    flock -u 8
    exec 8>&-
fi
