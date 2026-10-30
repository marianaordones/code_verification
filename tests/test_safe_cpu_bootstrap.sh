#!/usr/bin/env bash
# Test Python-without-pip flow against an existing CPU cache, without downloads.
set -Eeuo pipefail
repo="$(pwd)"
work="$(mktemp -d)"
trap '[[ -d "$work" && "${work##*/}" = tmp.* ]] && rm -rf -- "$work"' EXIT
project="$work/project"
mkdir -p "$project/scripts/cluster" "$work/home/pylibs"
cp scripts/cluster/setup_safe_cpu.sh "$project/scripts/cluster/"
printf 'mock requirement\n' > "$project/requirements-safe-cpu.txt"
cat > "$project/scripts/cluster/native_workspace.sh" <<'SH'
native_workspace() { NATIVE_WORKSPACE="$PROJECT_ROOT/native"; mkdir -p "$NATIVE_WORKSPACE"; export NATIVE_WORKSPACE; }
native_cleanup() { :; }
SH
cat > "$work/fake-python" <<'SH'
#!/usr/bin/env bash
if [[ "$1" == -c ]]; then
    [[ "$2" != *'print('* ]] || echo py312-x86_64-test
elif [[ "$1 $2" == '-m pip' ]]; then
    [[ "${PYTHONPATH:-}" == *'/pip'* ]] || exit 1
    echo 'mock pip available'
elif [[ "$1" == - ]]; then
    printf '# no network\n' > "$2"
elif [[ "$1" == */get-pip.py ]]; then
    [[ "$*" == *pip==25.0.1* ]]
    [[ "$2" == --target ]]
    mkdir -p "$3"
else
    echo 'Unexpected fake Python command' >&2; exit 95
fi
SH
chmod +x "$work/fake-python"
hash="$(sha256sum "$project/requirements-safe-cpu.txt" | awk '{print $1}')"
mkdir -p "$work/home/pylibs/safe-cpu-py312-x86_64-test-${hash:0:16}"
touch "$work/home/pylibs/safe-cpu-py312-x86_64-test-${hash:0:16}/.complete"
export HOME="$work/home" SLURM_SUBMIT_DIR="$project" CLUSTER_PYTHON="$work/fake-python"
flock() { :; }
export -f flock
# Source in a subshell because runtime installs its own EXIT cleanup hook.
(
    source "$project/scripts/cluster/setup_safe_cpu.sh"
    [[ "$PYTHONPATH" == *'/job-tmp/pip'* ]]
    python -m pip --version
)
echo 'Python without pip + cached CPU dependencies: bootstrap stays available for later Z3 installation: OK'
