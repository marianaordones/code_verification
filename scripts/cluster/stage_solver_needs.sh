#!/usr/bin/env bash
# Separate release: never overwrite the VerusBench tools-native bundle.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Source this helper after setup_runtime.sh" >&2
    exit 2
fi
source scripts/cluster/native_workspace.sh
native_workspace 2
python -m solver_needs_study.download tools --destination "$NATIVE_WORKSPACE/verus"
export VERUS_BIN="$NATIVE_WORKSPACE/verus/verus"
export Z3_BIN="$NATIVE_WORKSPACE/verus/z3"
export VERUS_Z3_PATH="$Z3_BIN"
export PATH="$HOME/.cargo/bin:$PATH"
if ! command -v rustup >/dev/null; then
    curl --fail --location --proto '=https' --tlsv1.2 https://sh.rustup.rs -o "$JOB_TMP/rustup-init.sh"
    bash "$JOB_TMP/rustup-init.sh" -y --no-modify-path --profile minimal --default-toolchain none
fi
# Probe without an implicit installation, which could trigger a self-update.
# HOME and /mnt/users may be aliases on this cluster; never replace rustup here.
export RUSTUP_AUTO_INSTALL=0
if ! rustup run 1.93.0 rustc --version >/dev/null 2>&1; then
    rustup toolchain install 1.93.0 --profile minimal --no-self-update
fi
rustup run 1.93.0 rustc --version
"$VERUS_BIN" --version
"$Z3_BIN" --version
