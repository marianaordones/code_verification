#!/usr/bin/env bash
# Source only from the CPU pilot job. Independent of the GPU runtime.
PROJECT_ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$PROJECT_ROOT"
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_TARGET PIP_PREFIX PIP_USER
export PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
export USE_TORCH=0 USE_TF=0 USE_FLAX=0
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 RAYON_NUM_THREADS=1
PYTHON_BIN=""
for candidate in "${CLUSTER_PYTHON:-}" python3.12 python3.11 python3; do
    [[ -n "$candidate" ]] || continue
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    [[ -n "$resolved" ]] || continue
    if "$resolved" -c 'import sys,platform; assert (3,11)<=sys.version_info[:2]<=(3,12); assert platform.system()=="Linux" and platform.machine()=="x86_64"' 2>/dev/null; then
        PYTHON_BIN="$resolved"; break
    fi
done
[[ -n "$PYTHON_BIN" ]] || { echo 'Set CLUSTER_PYTHON to Linux x86_64 Python 3.11/3.12.' >&2; return 21; }
command -v flock >/dev/null
source scripts/cluster/native_workspace.sh
native_workspace 3
JOB_TMP="$NATIVE_WORKSPACE/job-tmp"
mkdir -p "$JOB_TMP" logs "${HOME}/pylibs"
export TMPDIR="$JOB_TMP" PYTHON_BIN JOB_TMP PROJECT_ROOT
trap native_cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
# Some compute nodes have Python but no pip/ensurepip/venv. Bootstrap into local
# scratch, not system Python or a symlink-based virtualenv on the shared HOME.
safe_pip_path=""
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo "System pip unavailable; bootstrapping pip 25.0.1 in $JOB_TMP/pip"
    "$PYTHON_BIN" - "$JOB_TMP/get-pip.py" <<'PY'
import sys, urllib.request
urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', sys.argv[1])
PY
    "$PYTHON_BIN" "$JOB_TMP/get-pip.py" --target "$JOB_TMP/pip" --no-cache-dir 'pip==25.0.1'
    safe_pip_path="$JOB_TMP/pip"
fi
safe_pip=("$PYTHON_BIN" -m pip)
if [[ -n "$safe_pip_path" ]]; then
    safe_pip=(env "PYTHONPATH=$safe_pip_path" "$PYTHON_BIN" -m pip)
fi
req_hash="$(sha256sum requirements-safe-cpu.txt | awk '{print $1}')"
python_tag="$("$PYTHON_BIN" -c 'import sys,platform; print("py%d%d-%s-%s"%(*sys.version_info[:2],platform.machine(),"".join(platform.libc_ver())))')"
PROJECT_LIBS="${HOME}/pylibs/safe-cpu-${python_tag}-${req_hash:0:16}"
exec 9>"${PROJECT_LIBS}.lock"
flock 9
if [[ ! -f "$PROJECT_LIBS/.complete" ]]; then
    [[ ! -e "$PROJECT_LIBS" ]] || { echo "Incomplete CPU cache: $PROJECT_LIBS" >&2; return 22; }
    libs_stage="$(mktemp -d "${PROJECT_LIBS}.partial.XXXXXXXX")"
    "${safe_pip[@]}" install --ignore-installed --only-binary=:all: --target "$libs_stage" -r requirements-safe-cpu.txt
    PYTHONPATH="$libs_stage" "$PYTHON_BIN" - "$libs_stage" <<'PY'
import importlib.metadata as m, pathlib, sys
import transformers, tokenizers, huggingface_hub
assert transformers.__version__ == '4.51.3'
assert tokenizers.__version__ == '0.21.1'
root=pathlib.Path(sys.argv[1])
(root/'requirements-resolved.txt').write_text('\n'.join(sorted(f"{d.metadata['Name']}=={d.version}" for d in m.distributions(path=[str(root)]))))
(root/'.complete').write_text('CPU tokenizer only\n')
PY
    mv -T -- "$libs_stage" "$PROJECT_LIBS"
fi
flock -u 9
exec 9>&-
export PROJECT_LIBS PYTHONPATH="$PROJECT_ROOT:$PROJECT_LIBS${safe_pip_path:+:$safe_pip_path}"
python() { "$PYTHON_BIN" "$@"; }
export -f python
echo "SAFE CPU runtime: $PROJECT_LIBS (no GPU/LLM)"
