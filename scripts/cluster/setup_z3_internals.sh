#!/usr/bin/env bash
# Source after setup_runtime/stage_tools. Keep the Z3 API out of the LLM process.
Z3_INTERNALS_PYTHONPATH="${NATIVE_WORKSPACE:?}/z3-internals-python"
export Z3_INTERNALS_PYTHONPATH
python -m pip install --no-deps --only-binary=:all: \
    --target "$Z3_INTERNALS_PYTHONPATH" z3-solver==4.12.5.0 \
    > "logs/z3-internals-install-${SLURM_JOB_ID:-local}.log" 2>&1
python -m diagnostics.z3_internals selftest
