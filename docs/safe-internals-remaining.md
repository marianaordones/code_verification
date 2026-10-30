# SAFE: four jobs to finish the repair-row collection

The source contains **24,828 rows: 13,768 repair rows and 11,060 generation rows**. The two running 1,000-example jobs cover 2,000 distinct repair row IDs (the original pilot 200 is already included in the first 1,000, not another batch). The remaining count is **11,768**, divided into **four shards of 2,942**.

The previous pilots selected unique input programs. Completing the full dataset must also retain the remaining rows with duplicate input programs: all 13,768 repair rows represent 12,844 distinct input-code strings. A repeated input may have another diagnosis or teacher output. These rows are retained and processed independently. IDs do not overlap across the six batches; input hashes and families may overlap, and are not a train/test split.

## Submit all four independent CPU jobs

Add only the new files below to the cluster checkout. No shared collector code or existing fingerprinted selection/configuration is changed, so the first two jobs can continue:

```text
configs/safe-internals-remaining-a.json
configs/safe-internals-remaining-b.json
configs/safe-internals-remaining-c.json
configs/safe-internals-remaining-d.json
configs/safe-repair-remaining-a.json
configs/safe-repair-remaining-b.json
configs/safe-repair-remaining-c.json
configs/safe-repair-remaining-d.json
scripts/prepare_safe_internals_remaining.py
scripts/submit_safe_internals_remaining.sh
scripts/slurm/safe_internals_remaining.slurm
scripts/report_safe_full_coverage.py
scripts/submit_safe_full_coverage.sh
scripts/slurm/safe_full_coverage.slurm
tests/test_safe_remaining.py
```

From the repository root:

```bash
bash scripts/submit_safe_internals_remaining.sh
```

Optional argument 1 changes the dataset path; argument 2 changes the new output parent:

```bash
bash scripts/submit_safe_internals_remaining.sh "/path/sft_safe_25k.json"
```

The launcher prints four job IDs. They have no dependencies on each other or the first two jobs, and can run concurrently when resources permit. Each requests **4 CPUs, 32G RAM, high QoS, 24 hours, no GPU**, with two concurrent examples internally. Four new jobs therefore request a total of 16 CPUs and 128G RAM when all are running.

Outputs:

```text
results/safe-internals-remaining-attrs-v2/a/seed-20261018/
results/safe-internals-remaining-attrs-v2/b/seed-20261018/
results/safe-internals-remaining-attrs-v2/c/seed-20261018/
results/safe-internals-remaining-attrs-v2/d/seed-20261018/
```

Each output has the same report/master/exports layout as the first jobs. Both 12k/20x3 and 24k/50x3 views, SAFE attribute policy v2, actual input/target validation, assume tagging, strict implementation/contracts checks and `exports/validated/` filtering are unchanged. No model inference, fine-tuning, generation-example collection or whole-SMT-query prompting is added.

The dedicated selection driver applies a deterministic round-robin by historical diagnostic/isolation strata, preserves every remaining repair row and interleaves that order across four shards. It changes the selector only in its own preparation process, restoring it afterwards, and archives selection-driver provenance with the frozen inputs. Do not run generic `safe_internals prepare` directly for these shards: it would select from the beginning rather than excluding the first 2,000.

## Resume only one shard

Use the same dataset/output/code/tools. For example, resubmit only shard c:

```bash
bash scripts/submit_safe_internals_remaining.sh \
  data/safe/sft_safe_25k.json results/safe-internals-remaining-attrs-v2 c
```

Completed stages/records are reused. Never run two collectors against the same output. If a job times out or has missing results, resubmitting it is necessary before claiming complete enrichment. The frozen inclusion of the first 2,000 does not prove those jobs have finished successfully; their missing cases must also be resumed in their original jobs.

## Check completion of all 13,768 repair rows

After all six collection jobs finish:

```bash
bash scripts/submit_safe_full_coverage.sh
```

This is a small separate CPU reporting job (one-hour limit, no model/solver). Defaults point to the original first/second 1,000 outputs and the new remaining parent. Custom locations are supported:

```bash
bash scripts/submit_safe_full_coverage.sh \
  --first /path/first/seed-20261018 \
  --second /path/second/seed-20261018 \
  --remaining /path/remaining-parent
```

Read `analysis/safe-full-repair-coverage/coverage.md` and `coverage.json`. They verify selected IDs/dataset identities, count completed rows, internals availability, accepted targets and candidate positives for SFT across all six batches, and retain every missing ID. `complete: true` means all 13,768 repair records were evaluated, **not that every row produced internals or a valid target**. Compilation errors may have no SMT query, and invalid teacher outputs remain outside validated positives.

The 11,060 generation examples can remain unchanged for a later combined training export, as planned. The reporting job does not merge training files or choose splits; use the globally consistent family IDs and perform overlap/length checks before training. All original records remain in per-batch masters, including rejected targets and unavailable feedback.
