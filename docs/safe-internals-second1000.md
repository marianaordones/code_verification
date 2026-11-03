# SAFE: second independent batch of 1,000 repair inputs

This adds the next 1,000 unique repair input programs after the frozen first batch. Both row IDs and exact input-code hashes are disjoint. It does not mean the batches have no related program families; combine family metadata before any eventual train/validation split.

The new files do not edit the shared collector, its existing configurations, original selection, or original Slurm script. This avoids changing the first job's implementation fingerprint while it runs. The dedicated preparer changes the selection function only inside its own preparation process and restores it afterwards; collection uses the existing unmodified module. It archives the selection driver and its hash with the frozen evidence.

## Update and submit

If the first job is running, copy **only these new files** to the cluster:

```text
configs/safe-internals-second1000.json
configs/safe-repair-second1000.json
scripts/prepare_safe_internals_second1000.py
scripts/submit_safe_internals_second1000.sh
scripts/slurm/safe_internals_second1000.slurm
tests/test_safe_second1000.py
```

The first job must already have the SAFE v2/1000 collector from the previous change. Do not update unrelated shared modules during active jobs. From the repository root:

```bash
bash scripts/submit_safe_internals_second1000.sh
```

An existing dataset path and optional output override work as before:

```bash
bash scripts/submit_safe_internals_second1000.sh "/path/sft_safe_25k.json"
```

The job is independent, with no dependency on completion of the first batch. It can run concurrently when Slurm resources permit. **This is CPU-only; no second GPU is needed or requested.** Resources remain 4 CPUs, 32G RAM, high QoS, 24 hours and two concurrent examples per job. Both jobs reuse locked/cache-managed dependencies but have separate scratch directories and results.

The seed, model tokenizer, historical Verus/Z3, SAFE attribute policy v2, trust/preservation restrictions and the two packages (12k/20x3 and 24k/50x3) are unchanged. All selected examples are collected, regardless of eventual target acceptance. Positive exports retain only the previously defined verified/preserved criteria. No LLM inference or training occurs.

Output:

```text
results/safe-internals-second1000-attrs-v2/seed-20261018/report.md
results/safe-internals-second1000-attrs-v2/seed-20261018/summary.json
results/safe-internals-second1000-attrs-v2/seed-20261018/exports/validated/
```

The fixed IDs are in `configs/safe-repair-second1000.json` and copied into the output `selected_ids.json`. Reuse the same submission command to resume. To regenerate only the report:

```bash
bash scripts/submit_safe_internals_report.sh \
  results/safe-internals-second1000-attrs-v2/seed-20261018
```

Do not invoke the generic `safe_internals prepare` directly for this selection: it selects from offset zero. Use the dedicated submission/preparation driver. The generic `collect` and `report` commands remain compatible with the resulting frozen manifest.
