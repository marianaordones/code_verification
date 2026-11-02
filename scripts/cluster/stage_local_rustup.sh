#!/usr/bin/env bash
# Execute rustup from the already-tested node-local ELF filesystem. Keep the
# persistent RUSTUP_HOME/CARGO_HOME and all installed toolchains unchanged.
rustup_source="$(command -v rustup)"
[[ -f "$rustup_source" ]] || { echo "Cannot read rustup executable: $rustup_source" >&2; return 35; }
rustup_local_bin="${NATIVE_WORKSPACE:?Stage a native workspace before rustup}/rustup-bin"
mkdir -p "$rustup_local_bin"
if [[ "$(readlink -f "$rustup_source")" != "$(readlink -f "$rustup_local_bin/rustup" 2>/dev/null || true)" ]]; then
    cp -L -- "$rustup_source" "$rustup_local_bin/rustup"
    chmod 700 "$rustup_local_bin/rustup"
fi
export PATH="$rustup_local_bin:$PATH"
hash -r
rustup --version
echo "Node-local rustup: $(command -v rustup)"
