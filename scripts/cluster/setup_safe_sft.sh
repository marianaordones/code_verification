#!/usr/bin/env bash
# Reuse the tested pip bootstrap; install a separate, locked training cache.
source scripts/cluster/setup_safe_cpu.sh
export USE_TORCH=1 USE_TF=0 USE_FLAX=0
sft_hash="$(sha256sum requirements-safe-sft.txt | awk '{print $1}')"
sft_libs="${HOME}/pylibs/safe-sft-${python_tag}-${sft_hash:0:16}"
exec 8>"${sft_libs}.lock"
flock 8
if [[ ! -f "$sft_libs/.complete" ]]; then
    [[ ! -e "$sft_libs" ]] || { echo "Incomplete training cache: $sft_libs" >&2; return 22; }
    sft_stage="$(mktemp -d "${sft_libs}.partial.XXXXXXXX")"
    "${safe_pip[@]}" install --ignore-installed --only-binary=:all: --target "$sft_stage" -r requirements-safe-sft.txt
    PYTHONPATH="$sft_stage" "$PYTHON_BIN" - "$sft_stage" <<'PY'
import importlib.metadata as m, pathlib, sys
import torch, transformers, peft, bitsandbytes, accelerate
p = pathlib.Path(sys.argv[1])
(p/'requirements-resolved.txt').write_text('\n'.join(sorted(f"{d.metadata['Name']}=={d.version}" for d in m.distributions(path=[str(p)]))))
(p/'.complete').write_text('SAFE QLoRA runtime\n')
PY
    mv -T -- "$sft_stage" "$sft_libs"
fi
flock -u 8
exec 8>&-
export PYTHONPATH="$PROJECT_ROOT:$sft_libs"
export TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export TRITON_CACHE_DIR="$JOB_TMP/triton" TORCH_EXTENSIONS_DIR="$JOB_TMP/torch-extensions"
cp "$sft_libs/requirements-resolved.txt" "logs/safe-sft-packages-${SLURM_JOB_ID:-local}.txt"
