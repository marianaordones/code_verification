# Single-task bounded continuation

Run from the WSL checkout. This creates a separate study snapshot; the old
38 completed tasks, interrupted misc_bubble logs, manifest and code stay intact.
No source responses are reused or automatically retried. The new snapshot holds
the frozen inputs of the original selection, but executes only the named task.
Use `bounded-summary.json`, not the old 50-task comparison, to inspect this pilot.

```bash
cd ~/projects/code_verification
bash scripts/run_sonnet46_bounded.sh prepare
bash scripts/run_sonnet46_bounded.sh run
bash scripts/run_sonnet46_bounded.sh status
```

Default task: misc_bubble. Output:
`results/verusbench-sonnet46-bounded-misc-bubble-v1`.
Preparation does not call Claude. Run makes at most five model calls: one shared
first proposal and, if needed, two repairs in each arm. Each trajectory still
has three proposals. With a shared success, only one call is needed.

Sonnet 4.6 / Low, unchanged prompts, Verus/Lynette and internals 14,336 Qwen
tokens, 50 groups x 3 instances. The new external resource policy sends
CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192 after environment sanitation, and applies a
180-second local wall-clock limit per proposal. Thinking is included in the
output budget; 8192 is not an allocation just for the final source code.

Raw stdout/stderr are written immediately. A heartbeat is printed about every
10 seconds. The process group is terminated on an automatic user/continuation
event, a thinking estimate reaching the threshold, output truncation, unexpected
tools/compaction, or timeout. Local observation/termination cannot guarantee zero
additional server tokens: a CLI continuation may already have begun before its
event reaches the runner. No response is automatically resubmitted.

A resource stop returns an empty proposal, consumes the corresponding proposal,
and keeps the current candidate for verification and subsequent repair. Raw logs
and response.resource_stop_reason distinguish this from mathematical rejection.
Quota, authentication, malformed stream or other infrastructure failures stop
the run; they are not silently turned into proof failures. A saved receipt
without response blocks resubmission until inspected. Completed responses are
reused on rerun, so `run` does not repeat completed model calls.

The 180 seconds concern model inference only. Local verification and Z3 replay
have their existing separate timeouts. Five calls can use up to 15 minutes of
inference; neither this nor Low guarantees a particular subscription percentage.

For a later single task use the same --task and --output arguments on all three
commands. Keep this policy version separate from the earlier unlimited-output
results. Do not merge it silently into the original comparison.

No-provider tests:
```bash
source .venv/bin/activate
python -m unittest tests.test_claude_bounded
```
