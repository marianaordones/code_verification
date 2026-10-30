# Restart the 362-task complement study after pre-inference fingerprint failure

The archived failed run contains all 362 prepared inputs and initial replay pools, but no model requests/responses, task results, run.json or sessions. A completed Slurm job is not necessarily a successful experiment: job 13268 failed in `validate()` before inference because the current `solver_needs_study/feedback.py` differed from preparation.

Do not erase results, edit hashes in the manifest, disable validation, or resubmit only the GPU job against the old manifest. A new preparation must record the current implementation.

From the repository root, copy the new launcher and submit:

```bash
bash scripts/resubmit_solver_needs_complement16k_remaining.sh
```

Defaults:

- Original completed base24k/50x3 evidence: `results/solver-needs-qwen14b-remaining362-internals24k/seed-20261018`.
- Old prepared parent/pool: `results/solver-needs-qwen14b-remaining362-complement16k-single/seed-20261018`.
- NEW output parent: `results/solver-needs-qwen14b-remaining362-complement16k-single-rerun/seed-20261018`.

If paths differ, provide those three arguments in the same order. The launcher requires all 362 saved pool manifests before submitting. It submits the existing preparation/GPU/comparison jobs with dependencies, overriding comparison time to one hour, same single arm, frozen 362 IDs, three proposals, base24k/50x3 + complement16k, 61,440 context tokens and frozen system prompt/seeds. No control arm is added.

Preparation revalidates the original evidence, source settings/common prompts and tool identities, copies the same candidate/query evidence, validates pool input/worker/ranking/inventory signatures and hashes, and rebuilds packet files/manifest under the current code. Matching completed pools are reused without new initial replays. If source files, collector, tools or pool provenance differ, preparation fails explicitly rather than blessing changed evidence. Later model repair candidates still require new verification/replays normally.

Do not change the checkout while these jobs are queued or running. Other jobs may run concurrently from the same unchanged code, but updates to hashed source files can invalidate queued studies. Use another checkout for further development during this run. This launcher adds no changes to the shared collector or its fingerprints itself.

Read the GPU `.err` and `.out`, not only the comparison logs. `sacct -j JOBID --format=JobID,JobName%30,State,ExitCode,Elapsed` must show successful exit; a job merely leaving the queue is not evidence of completion.

Default report:

```text
results/solver-needs-qwen14b-remaining362-complement16k-single-rerun/seed-20261018/study/comparison.md
```

`single_arm=with_internals` schedules only base24k + complement16k. Reports correctly identify the single arm.
