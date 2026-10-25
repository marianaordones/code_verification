# Repeat the five-program pilot with Sonnet 5.5

Configuration `configs/verusbench-sonnet5.json` differs from Opus only in model:
`claude-sonnet-5-5`. Low effort, three total proposals per arm, same five originals,
same prompts, extraction policy, verification, integrity and feedback budgets.

Preparation imports only `inputs/` from the completed Opus study after verifying
all frozen file hashes, the prompt hashes, selection, configuration and tools.
It does not load/copy the Opus response directories or select tasks by outcomes.
Initial diagnostics and internals are byte-identical; no new initial replay.
Subsequent failed candidates get their own diagnostics and treatment replay.

Run in WSL after syncing the new files (already-installed tools are reused):

```bash
cd ~/projects/code_verification
bash scripts/run_verusbench_sonnet.sh prepare
bash scripts/run_verusbench_sonnet.sh run
cat results/verusbench-sonnet5-low-v1/comparison.md
```

`prepare` does not call the model. `run` uses the official Pro login and sends up
to 30 real requests. No model-menu change needed. Keep extra paid usage disabled.
The shared transport verifies the actual model in the saved stream transcript.
An unavailable model causes an error, not an automatic switch to Opus.

The source defaults to `results/verusbench-claude5-low-v2`. Override with
`VB_SOURCE_STUDY=/absolute/path bash scripts/run_verusbench_sonnet.sh prepare`
if your completed Opus study is elsewhere. Use a new destination if it already
exists or the configuration changes; existing results are never overwritten.

Preserve the old source snapshot to resume or regenerate older Opus reports:
implementation hashes change with this generalized runner. The existing Opus
result files and reports remain intact. Compare within-model with/without
internals first; a five-task sample cannot support a general performance claim.
