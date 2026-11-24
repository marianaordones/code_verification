#!/usr/bin/env bash
set -Eeuo pipefail
repo="$(pwd -P)"
mkdir -p "$repo/.cluster"
work="$(mktemp -d "$repo/.cluster/local-rustup-test.XXXXXXXX")"
cleanup() {
    case "$work" in "$repo"/.cluster/local-rustup-test.*) [[ ! -L "$work" ]] && rm -rf -- "$work" ;; esac
}
trap cleanup EXIT
mkdir -p "$work/shared" "$work/native"
cat > "$work/shared/rustup" <<'SH'
#!/usr/bin/env bash
# Simulate a shared path that can be read but cannot run correctly.
[[ "$0" == "$NATIVE_WORKSPACE/rustup-bin/rustup" ]] || exit 22
[[ "$1" == --version ]] || exit 23
echo 'rustup mock from native scratch'
SH
chmod +x "$work/shared/rustup"
export NATIVE_WORKSPACE="$work/native"
export PATH="$work/shared:$PATH"
if rustup --version; then echo 'Mock must fail on shared storage' >&2; exit 1; fi
source scripts/cluster/stage_local_rustup.sh
[[ "$(command -v rustup)" == "$work/native/rustup-bin/rustup" ]]
cmp "$work/shared/rustup" "$work/native/rustup-bin/rustup"
# Re-sourcing must not try to copy a file onto itself.
source scripts/cluster/stage_local_rustup.sh
echo 'Node-local rustup staging: OK'
