# SAFE enriched SFT

One enriched training dataset; no paired control dataset is produced. Defaults:
Qwen2.5-Coder-14B-Instruct at pinned revision aedcc2d42b622764e023cf882b6652e646b95671,
50x3 / 24,576 internal tokens, 32,768 total training tokens, single GPU QLoRA NF4,
BF16 computation, rank 16 / alpha 32 / dropout .05, all linear layers, one epoch,
batch 1 / accumulation 16, learning rate 1e-4, cosine schedule / 3% warmup.
These are initial settings, not validated GPU feasibility or tuned hyperparameters.

## Data

Preparation reads the six existing repair batches, including completed d, without
executing Verus or changing any collection. It requires complete repair coverage by
default; `--allow-partial` is explicit pilot-only behavior. Saved eligible targets
must verify, preserve the program, and have no assume calls. Included categories:
internals available in the selected package; frontend errors with no captured
queries or capture errors. Other no-internals cases remain excluded.
Frontend examples retain Verus diagnostics and explicitly state that internals are
unavailable. Saved solver interpretation guidance is preserved.

Generation examples are included only with a separate validation file. Submit:

```bash
bash scripts/submit_safe_sft.sh validate-generation
```

This CPU job checks all 11,060 generation answers using historical Verus 33269ac,
checks preservation with the SAFE attribute policy, rejects forbidden constructs,
and saves individual results for resume. It does not infer new answers or collect
internals. A time limit can require resubmitting the same command. Changing tool
hashes requires a new output directory. The aggregate validation.json appears at
the end; verifier infrastructure failures must be investigated before treating
the validation as final.

Then prepare the final training data (CPU job):

```bash
bash scripts/submit_safe_sft.sh prepare \
  --generation-validation results/safe-generation-validation/validation.json
```

Omit `--generation-validation` for a repairs-only pilot. Do not overwrite that
pilot directory when later adding generation; use `--output data/safe/sft-enriched-v2`.
The default destination is `data/safe/sft-enriched-v1`. It contains train.jsonl,
validation.jsonl, and a manifest with hashes, excluded IDs, and overlap results.
No data are uploaded or published.

The split is a seeded 95/5 hash over families, joining exact source/target/label
components and comment/whitespace-normalized programs. Generation and repairs are
joined before splitting. This does not establish semantic independence between
program variants. Benchmark flags propagate to the entire connected family.

## Benchmark screening

`scripts/safe_sft_data.py --overlap-only --output analysis/safe-verusbench-overlap`
checks both SAFE source and target against all 150 local manifest programs.
It checks token-exact equality and flags at least 80% containment of benchmark
12-token shingles. Near matches require review; renamed/structurally rewritten
variants may be missed. The preparation excludes every flagged family by default.
Local screening found 34 flagged SAFE rows (52 source/target-task matches), zero
token-exact matches, and zero parse errors. Inspected examples include variants of
diffy_brs3, misc_map, and misc_tail_triangle. This is not proof of no further leakage.

## GPU smoke test and training

```bash
bash scripts/submit_safe_sft.sh smoke \
  --data data/safe/sft-enriched-v1 --output results/safe-sft-smoke-v1
```

This runs two optimizer steps on the longest training example, then evaluates the
longest validation example. Check logs and metrics.json before submitting training:

```bash
bash scripts/submit_safe_sft.sh train \
  --data data/safe/sft-enriched-v1 --output results/safe-sft-v1
```

Training defaults to high_performance / high, one GPU, 64G host RAM, 48h limit.
Optional environment variables on submission: SFT_GPU_TYPE (exact Slurm GPU
type), SFT_PARTITION and SFT_NODE. Inspect `sinfo -N -o '%N %P %G %f'` first.
For example, only if the configured type is a100_80gb:
`SFT_GPU_TYPE=a100_80gb bash scripts/submit_safe_sft.sh smoke --output results/safe-sft-smoke-a100-v2`.
An A100 may have 40GB or 80GB; its name alone is insufficient to establish capacity.
The custom internal model forward explicitly enables CUDA BF16 autocast, since
it bypasses Accelerate's outer forward wrapper. Allocator expandable segments are
enabled to reduce fragmentation. Neither change guarantees that 32k fits on L40S.
After an OOM, rerun the smoke test in a new output directory, not the failed one.
Do not request two GPUs with this single-GPU trainer: DDP does not pool memory for
one example, and model/FSDP sharding would require a separate implementation.
It uses a separate pinned dependency cache, not the vLLM environment. Model files
reuse the existing .cluster/models download without symlinks. Full training has
not been executed here. L40S memory feasibility and duration require the smoke
test. No automatic token truncation or example dropping occurs. If any example
exceeds 32,768 tokens, preparation of model inputs fails explicitly.

Loss covers only the final assistant answer, including its terminating chat
tokens. Prompts and diagnostics are masked. A chunked checkpointed linear-head
cross entropy avoids materializing the full sequence-by-vocabulary logits tensor;
it still uses the complete program/context. No packing. Checkpoints every 100
optimizer steps, two retained, final adapter/tokenizer under adapter/.

Resume the same data/config/code with an explicit checkpoint:

```bash
bash scripts/submit_safe_sft.sh train --data data/safe/sft-enriched-v1 \
  --output results/safe-sft-v1 --resume results/safe-sft-v1/checkpoint-100
```

Pending checks: finish final collection audit, run generation validation, review
overlap flags and potential variants, check split composition, run GPU smoke test,
then evaluate the trained adapter with actual Verus verification. Validation loss
is not a proof success rate. Additional evaluation on Solver Needs requires its
own overlap screening; only VerusBench is screened by this version.
