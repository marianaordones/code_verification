#!/usr/bin/env bash
# Test only mocked rustup; no downloads or changes to the real Rust installation.
set -Eeuo pipefail
repo="$(pwd)"
work="$(mktemp -d)"
trap '[[ -d "$work" && "${work##*/}" = tmp.* ]] && rm -rf -- "$work"' EXIT
mkdir -p "$work/home/.cargo/bin" "$work/job"
export HOME="$work/home" CARGO_HOME="$work/home/.cargo" JOB_TMP="$work/job"
export SAFE_RUST_TEST_LOG="$work/calls" SAFE_RUST_TEST_READY="$work/ready"
cat > "$HOME/.cargo/bin/rustup" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SAFE_RUST_TEST_LOG"
if [[ "$1" = run ]]; then
    [[ -f "$SAFE_RUST_TEST_READY" ]] || exit 1
    echo 'rustc 1.76.0 (mock)'
elif [[ "$1 $2" = 'toolchain install' ]]; then
    [[ "$*" = *--no-self-update* ]] || exit 91
    touch "$SAFE_RUST_TEST_READY"
else
    exit 92
fi
SH
chmod +x "$HOME/.cargo/bin/rustup"
touch "$SAFE_RUST_TEST_READY"
PATH=/usr/bin:/bin
source "$repo/scripts/cluster/setup_safe_rust.sh"
[[ "$RUSTUP_AUTO_INSTALL" = 0 ]]
! grep -q '^toolchain install' "$SAFE_RUST_TEST_LOG"
rm -- "$SAFE_RUST_TEST_READY"
: > "$SAFE_RUST_TEST_LOG"
source "$repo/scripts/cluster/setup_safe_rust.sh"
grep -q '^toolchain install 1.76.0-x86_64-unknown-linux-gnu.*--no-self-update' "$SAFE_RUST_TEST_LOG"
echo 'SAFE Rust PATH reuse and missing-toolchain installation: OK'
