# VerusBench: five original inputs, Opus 5.5, Low

## Task and decisions

This is proof completion from the original **unverified** programs, not repair of
saved Qwen candidates. Three total proposals **per program and per arm**, including
the first generation. Maximum 30 model calls. Stop an arm after whole-file success.
No seed or temperature control; adaptive effort explicitly Low. The transport
does not enforce a 4,096 Claude output-token cap. That number is the Qwen-token
reserve used for prompt budgeting, not an equal-compute guarantee.

Both arms receive the original unverified program, current candidate, Verus and
integrity diagnostics, source failure context, and an explicit attempt history.
The initial program is checked once before any generation, so initial diagnostics
are available to both arms. Only treatment receives the internals block. Later
trajectories generate their own diagnostics; never replay stale internals as current.
Arms alternate order by task. No verified reference solutions are loaded.

The model returns a complete annotated file, using `prompts/v4/system.txt`.
Proof completion may require adding invariants and proof annotations in several
locations; the old localized single-site action is not used in this experiment.
The original executable implementation, specifications and contracts remain
authoritative. Existing `IntegrityValidator` combines lexical guards and the
vendored Lynette AST comparison. Success requires both this check and Verus on
the complete file. No catalogue insertion, NLA flag, new assumptions, tools or
retrieval are available to the model. An invalid or unchanged output consumes one
proposal. Direct source or a single rust/verus/rs code fence can be extracted;
malformed/multiple fences are rejected. No extra model formatting-repair call.

## Frozen selection

`configs/verusbench-claude5-selection.json` lists five programs from the official
150-input inventory at benchmark commit cbf9c0c6337b224fd8e5b7cb4e01ae65c0f98bc1.
ID-sorted category pools are shuffled with seed 20261024, then interleaved.
No difficulty, previous outcomes or Claude results are consulted. The selected
original contents must be distinct; there are four categories, hence one has
two programs. This five-case engineering pilot is not a benchmark-wide estimate.

- cloverbench_linear_search2 (CloverBench)
- diffy_s22if (Diffy)
- mbpp_task_id_557 (MBPP)
- misc_findmax (Misc)
- cloverbench_array_concat_strong (CloverBench)

All five are frozen before local verification. Already-verifying originals are
recorded separately and receive no model calls; they are not silently replaced.

## Tools and internals

Use the original baseline's Verus commit 33269ac6a0ea33a08109eefe5016c1fdd0ce9fbd,
Z3 4.12.5, and vendored patched Lynette. Do not reuse the solver-needs Verus bundle.
The setup wrapper reuses `scripts/cluster/setup_tools.sh` locally, with the
repository root supplied through its legacy SLURM_SUBMIT_DIR variable; no Slurm
job is submitted. Rust builds use one job to reduce memory pressure. The source
build may take substantial time and needs network access and at least 25 GiB
scratch space. An existing validated `.cluster/tools-native.tar.gz` is reused.
Tool identities and API library hashes are checked at prepare and run.

Capture/replay and selection reuse `repair_study.feedback.build_payload`: first
SAT/UNKNOWN query, five-second diagnostic replay, outcome agreement required,
up to 24 quantifier groups and four instances per group, 12,288 Qwen-token budget.
This is the older repair-study selector, not the solver-needs three-query/20x3
selector. Both are heuristic diagnostic replays, not original solver search.
The source context remains common to both arms. Base-plus-feedback must fit the
same 49,152 Qwen-token envelope; oversized sources are errors, never truncated.
The reused builder conservatively checks fit against its existing full/local
contracts; the actual generation prompt is additionally checked before each call.

## WSL commands

Copy `verusbench_study/`, `configs/`, `scripts/`, `tests/`, `data/`, and
`tools/lynette/` into the WSL project, preserving the existing source dependencies.

```bash
cd ~/projects/code_verification
source .venv/bin/activate
python -m pip install -r requirements-claude-local.txt
python -m unittest discover -s tests -p test_verusbench_claude.py
bash scripts/setup_verusbench_local.sh
bash scripts/run_verusbench_claude.sh prepare
# The next command sends actual model requests, up to 30, using the Pro login:
bash scripts/run_verusbench_claude.sh run
cat results/verusbench-claude5-low-v2/comparison.md
```

Keep extra paid usage disabled in the Claude account. Native subscription
authentication, no tools, no customizations and no automatic retries are enforced
by the shared Claude transport. Preparation never calls Claude. On a quota or
infrastructure error, stop and inspect the raw transcript. Do not automatically
remove pending-call receipts or resubmit an ambiguous completed request.

Repeat `run` to reuse saved responses and completed proposals after an ordinary
interruption. Runtime/CLI identity, implementation and frozen input hashes must
match; otherwise use a new study directory. Do not update CLI/code during a run.
`compare` reads the current state without model calls. Per-attempt request,
transcript, response, candidate, integrity, verification, format and failure records
are preserved. Comparison JSON includes exclusive successes and first-pair checks.
Rates must not be directly equated to localized solver-needs repair rates.

## Corrected prompt (v2 study directory)

`prompts/verusbench-claude/solver-info.txt` is scoped to this experiment, so the
older repair study retains its original prompt. The new text specifies the
12,288-token feedback budget, measured with the Qwen tokenizer, and explicitly
states that only treatment receives internals. Both arms initially receive the
same original unverified source and conventional diagnostics. Later trajectories
may diverge. The new prompt is included in the frozen implementation hashes.

After copying the updated sources into WSL, run `prepare` again using the new
default directory `results/verusbench-claude5-low-v2`. Do not overwrite or resume
the old v1 preparation with the corrected code. Tools, dependencies, selected
IDs, Low effort and three proposals per arm are unchanged. No tool rebuild needed.
