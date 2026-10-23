#!/usr/bin/env bash
# Persist source/bundles on shared storage; build executable artifacts locally.
set -Eeuo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
PROJECT_ROOT="$PWD"
# The old Cargo bundled with Verus can fail to fetch Git revisions through
# libgit2. Use the system Git, which can fetch the pinned getopts commit.
export CARGO_NET_GIT_FETCH_WITH_CLI=true
mkdir -p .cluster
exec 8>.cluster/tools.lock
flock 8
auto_build=0
if [[ -z "${VERUS_BIN:-}${Z3_BIN:-}${LYNETTE_BIN:-}" && -f .cluster/tools-native.json && -f .cluster/tools-native.tar.gz ]]; then
    python - <<'PY'
import hashlib,json,pathlib
m=json.loads(pathlib.Path(".cluster/tools-native.json").read_text())
assert m["complete"] and hashlib.sha256(pathlib.Path(".cluster/tools-native.tar.gz").read_bytes()).hexdigest()==m["sha256"], "Invalid native tool bundle"
PY
    echo "Reusing complete native tool bundle; no Rust rebuild needed."
    exit 0
fi
if [[ -n "${VERUS_BIN:-}" || -n "${Z3_BIN:-}" || -n "${LYNETTE_BIN:-}" ]]; then
    : "${VERUS_BIN:?Set all three tool paths, or none for automatic setup}"
    : "${Z3_BIN:?Set all three tool paths, or none for automatic setup}"
    : "${LYNETTE_BIN:?Set all three tool paths, or none for automatic setup}"
else
    auto_build=1
    for tool in git cc make; do
        command -v "$tool" >/dev/null || { echo "Tool preparation requires $tool on $(hostname)." >&2; exit 30; }
    done
    source scripts/cluster/native_workspace.sh
    native_workspace 25
    trap native_cleanup EXIT
    mkdir -p "$NATIVE_WORKSPACE/tmp"
    export TMPDIR="$NATIVE_WORKSPACE/tmp"
    # Vargo builds its own executable before invoking Verus's build. Keeping
    # only a top-level Cargo target override is insufficient for all its paths.
    unset CARGO_TARGET_DIR CARGO_BUILD_TARGET_DIR
    export PATH="${HOME}/.cargo/bin:${PATH}"
    if ! command -v rustup >/dev/null; then
        # User-level installation, no sudo or modules. Requires HTTPS access.
        command -v curl >/dev/null || { echo "Install rustup in HOME or provide VERUS_BIN/Z3_BIN/LYNETTE_BIN. curl is missing." >&2; exit 31; }
        curl --fail --location --proto '=https' --tlsv1.2 https://sh.rustup.rs -o "${TMPDIR:?}/rustup-init.sh"
        bash "$TMPDIR/rustup-init.sh" -y --no-modify-path --profile minimal --default-toolchain stable
    fi
    # Keep Cargo's Git object databases on native storage as well. A new cache
    # avoids carrying incomplete/shared-filesystem objects into this build.
    # Set this AFTER installing rustup so the Rust installation stays persistent.
    export CARGO_HOME="$NATIVE_WORKSPACE/cargo-home"
    mkdir -p "$CARGO_HOME"
    echo "cargo_home=$CARGO_HOME; Git dependencies fetched with system Git"
    revision=33269ac6a0ea33a08109eefe5016c1fdd0ce9fbd
    checkout="$PROJECT_ROOT/.cluster/verus"
    if [[ ! -d "$checkout/.git" ]]; then
        git clone https://github.com/verus-lang/verus.git "$checkout"
    fi
    actual="$(git -C "$checkout" rev-parse HEAD)"
    # Only set the requested revision on a newly prepared clone. A completed
    # checkout at a different revision is a configuration error, not a reset.
    if [[ ! -f .cluster/verus-setup-revision ]]; then
        git -C "$checkout" checkout "$revision"
        printf '%s\n' "$revision" > .cluster/verus-setup-revision
    elif [[ "$actual" != "$revision" ]]; then
        echo "Verus checkout changed: expected $revision, found $actual. Inspect .cluster/verus." >&2
        exit 32
    fi
    local_checkout="$NATIVE_WORKSPACE/verus-source"
    git clone --no-hardlinks "$checkout" "$local_checkout"
    git -C "$local_checkout" submodule update --init --recursive
    if [[ ! -x "$local_checkout/source/target-verus/release/verus" ]]; then
        (
            cd "$local_checkout/source"
            # Upstream activation sets its pinned Rust toolchain and vargo PATH.
            # Disable nounset only for the upstream activation script.
            set +u
            source ../tools/activate
            set -u
            # Same release as this Verus revision's get-z3.sh. Python's zipfile
            # avoids depending on the system unzip command on compute nodes.
            python "$PROJECT_ROOT/scripts/cluster/download_z3.py" "$PWD/z3"
            vargo build --release
        )
    fi
    # The parser uses its own Cargo.lock and a newer Rust toolchain than Verus.
    mkdir -p "$NATIVE_WORKSPACE/lynette-source"
    tar -C "$PROJECT_ROOT/tools/lynette/source" --exclude=./target -cf - . \
        | tar -C "$NATIVE_WORKSPACE/lynette-source" -xf -
    CARGO_TARGET_DIR="$NATIVE_WORKSPACE/lynette-target" rustup run stable cargo build --locked --release \
        --manifest-path "$NATIVE_WORKSPACE/lynette-source/Cargo.toml"
    mkdir -p "$NATIVE_WORKSPACE/bundle/verus"
    # Preserve the entire Verus distribution, including libraries/vstd, and
    # dereference build-time symlinks so they cannot point to deleted scratch.
    cp -RL "$local_checkout/source/target-verus/release/." "$NATIVE_WORKSPACE/bundle/verus/"
    cp -L "$local_checkout/source/z3" "$NATIVE_WORKSPACE/bundle/verus/z3"
    cp "$NATIVE_WORKSPACE/lynette-target/release/lynette" "$NATIVE_WORKSPACE/bundle/lynette"
    VERUS_BIN="$NATIVE_WORKSPACE/bundle/verus/verus"
    Z3_BIN="$NATIVE_WORKSPACE/bundle/verus/z3"
    LYNETTE_BIN="$NATIVE_WORKSPACE/bundle/lynette"
fi

for executable in "$VERUS_BIN" "$Z3_BIN" "$LYNETTE_BIN"; do
    [[ "$executable" == /* && -x "$executable" ]] || { echo "Expected an absolute executable path: $executable" >&2; exit 33; }
done
"$VERUS_BIN" --version
"$Z3_BIN" --version
"$LYNETTE_BIN" --help >/dev/null
python - "$VERUS_BIN" "$Z3_BIN" "$LYNETTE_BIN" <<'PY'
import hashlib,json,pathlib,subprocess,sys
from baseline.storage import write_json
names = ("VERUS_BIN", "Z3_BIN", "LYNETTE_BIN")
data = {name:{"path":value,"sha256":hashlib.sha256(pathlib.Path(value).read_bytes()).hexdigest()} for name,value in zip(names,sys.argv[1:])}
version = subprocess.run([sys.argv[1], "--version"],text=True,capture_output=True,check=True)
assert "33269ac" in version.stdout + version.stderr, "Unexpected Verus revision"
data["complete"] = True
write_json(".cluster/tools.json",data)
PY
if [[ "$auto_build" == 1 ]]; then
    tar -czf .cluster/tools-native.tar.gz.partial -C "$NATIVE_WORKSPACE/bundle" .
    mv -f .cluster/tools-native.tar.gz.partial .cluster/tools-native.tar.gz
    python - <<'PY'
import hashlib,pathlib
from baseline.storage import write_json
archive=pathlib.Path(".cluster/tools-native.tar.gz")
write_json(".cluster/tools-native.json", {"complete":True, "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
           "verus_revision":"33269ac6a0ea33a08109eefe5016c1fdd0ce9fbd", "execution":"extract to native scratch for each job"})
PY
fi
echo "TOOL SETUP PASSED: tools validated; automatic builds saved as .cluster/tools-native.tar.gz"
