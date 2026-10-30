#!/usr/bin/env bash
# The historical Verus binary needs Rust 1.76 even for CPU-only collection.
# Keep existing rustup; HOME and /mnt/users may name the same installation.
export PATH="${CARGO_HOME:-${HOME}/.cargo}/bin:${HOME}/.cargo/bin:${PATH}"
export RUSTUP_AUTO_INSTALL=0
if ! command -v rustup >/dev/null; then
    curl --fail --location --proto '=https' --tlsv1.2 https://sh.rustup.rs -o "$JOB_TMP/safe-rustup-init.sh"
    bash "$JOB_TMP/safe-rustup-init.sh" -y --no-modify-path --profile minimal --default-toolchain none
fi
safe_rust_version=1.76.0-x86_64-unknown-linux-gnu
if ! rustup run "$safe_rust_version" rustc --version >/dev/null 2>&1; then
    rustup toolchain install "$safe_rust_version" --profile minimal --component rustc-dev --no-self-update
fi
rustup run "$safe_rust_version" rustc --version
