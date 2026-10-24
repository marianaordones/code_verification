# Claude local via WSL: exploratory paired repair

This route uses the unmodified official Claude Code CLI with the user's native
claude.ai Pro login. No API key, Slurm, CUDA, vLLM or model weights are used.
Keep extra paid usage disabled in your Claude account if you want included usage
only; this runner cannot control account billing settings.

## Frozen protocol

- `claude-opus-5-5`, explicit `medium` effort, three total proposals per task/arm.
- Same local proof slot, parser, law catalogue, NLA option and whole-file verifier
  as the Qwen study. Invalid/empty/repeated actions consume proposals.
- Same 49,152 Qwen-token input budget including 4,096 reserved tokens, 12,288
  Qwen-token internals budget, 20 groups, three instances, three failing queries.
  Only the pinned Qwen tokenizer is downloaded, not its weights.
- The token budget controls feedback selection; it is NOT a Claude context count.
  **Claude output does not have a hard 4,096-token cap in this transport.**
  Adaptive reasoning is controlled by medium effort. Seed and temperature are
  uncontrolled and logged as null. This is an exploratory comparison with these
  explicit resource differences, not an equal-compute experiment.
- Every request starts a fresh process in an empty temporary directory with a
  custom system prompt, `--safe-mode`, no built-in or MCP tools, no settings
  sources and no session persistence. Protocol history is explicit in the prompt.
  Managed administrator policies can still apply to the official client.
- Extraction policy `single-json-action-v2` is shared with Qwen and both arms.
  Accept a direct JSON object, or exactly one triple-backtick `json` block with
  explanatory prose before/after. For compatibility, a standalone unlabelled
  triple-backtick block is also accepted, but cannot have surrounding prose.
  Reject multiple/unclosed/other-language fences, object braces outside the block,
  duplicate keys and malformed JSON. Do not repair JSON or choose a preferred block.
  All four-field schema, law and proof-slot restrictions still apply.
  `response-format.json` records extraction mode and strict direct-JSON adherence
  separately from action validity. Invalid actions still consume proposals.
- The stream transcript is saved and checked for unexpected model changes,
  tool availability/use, and context compaction. No schema-constrained generation
  or additional JSON repair turn is used.
- Preparation uses the existing published-validation policy. Initially verified
  candidates are reported separately. Replay internals are newly generated locally;
  they are not guaranteed equal to previous cluster events.

## Set up and smoke test

Run in the WSL project, after installing Rust 1.93.0, the pinned Verus bundle,
the dataset, and logging into Claude Code in WSL:

```bash
source .venv/bin/activate
python -m pip install -r requirements-claude-local.txt
python -m solver_needs_study.claude_code
python -m unittest discover -s tests -p 'test_claude_code.py'
bash scripts/run_claude_local.sh prepare results/claude-local-smoke 1
```

None of these commands sends a model request. `prepare` downloads only tokenizer
files and generates Verus/Z3 diagnostics for the first ID in the fixed 100 list.
This is a pipeline smoke test, not a newly selected representative pilot.

The following command **sends real model requests**, up to six for one task:

```bash
bash scripts/run_claude_local.sh run results/claude-local-smoke
```

The first run checks subscription authentication and freezes CLI binary/version,
Python and dependency versions. A different runtime cannot resume the same study.
An update to the client requires a new study directory; do not silently mix it.
The report is `results/claude-local-smoke/comparison.md` plus `comparison.json`.

The first pair must have equal candidate/common-prompt hashes and null seeds;
only the internals block differs. Per-attempt `request.json`, `exposure.json`,
`claude-stdout.jsonl`, `claude-stderr.txt`, `response.json`, `candidate.rs`, and
`verification.json` permit auditing.

## Resume and failures

Repeat `run` to reuse saved responses and completed proposals. A quota/authentication/
CLI/transport failure stops the whole batch, without finalizing a failed model
proposal and without automatically resubmitting. Raw transcripts remain on disk.

A `claude-call.json` marked started, timed_out, or nonzero exit blocks resubmission.
Inspect its transcript first: a timed-out request may already have consumed usage.
If explicitly choosing to resubmit that same pending request, rename the receipt
to a unique archive name (and preserve the old stdout/stderr under unique names)
before rerunning. Never delete `request.json` or modify the prompt to resume.
A successful saved CLI call is parsed again without a new request; model/tool
audit failures must be investigated, not bypassed.

Use a separate study directory for a pilot with a preselected sample. For Qwen
comparison, restrict Qwen results to its first three proposals. Local replays,
uncontrolled sampling and different output/reasoning resources remain limitations.

## Auditing responses from an older parser

Do not resume or overwrite an old study after changing extraction policy. Freeze
the new policy through the implementation hashes of a NEW prepared study. You can
independently reapply old saved responses without sending any model requests:

```bash
export VERUS_BIN="$PWD/.local-tools/verus/verus"
export Z3_BIN="$PWD/.local-tools/verus/z3"
python -m solver_needs_study.audit_responses \
  --study results/claude-local-smoke \
  --output results/claude-local-smoke-format-audit-v2
```

The audit output must be a new directory outside the original study. Original
input hashes and verifier/API identities must match. Actions are rendered and
whole-file verified in the audit directory, with equivalent candidate/NLA pairs
verified once. `report.json` reports each saved response independently. It does
not replace the original scores or simulate feedback trajectories that would
have changed after earlier acceptance. No Claude authentication is required.

Do not copy these code changes into an active cluster run: existing manifests
freeze implementation hashes. Preserve its original checkout for resumption.
