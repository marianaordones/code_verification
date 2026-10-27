# Three advanced-feedback arms

Submit from the cluster repository root:

```bash
bash scripts/submit_solver_needs_blocks12k.sh
```

Optional arguments: completed ORIGINAL 24k/50x3 study directory, then output parent.
Default source: `results/solver-needs-qwen14b-100-internals24k/seed-20261018`.
Default destination: `results/solver-needs-qwen14b-100-blocks12k/seed-20261018/study`.
The existing Slurm preparation/run/comparison jobs are reused (QoS high). One GPU loads the model once for all three arms. Preparation is CPU-only. No inference is executed locally.

Same frozen 100 IDs, Qwen revision, prompt, seeds, three proposals and 65536 context. Every arm receives the identical initial base24k50x3 + complement12k, including up to20 unobserved quantifiers. Each new block has a global 12288-token limit across up to3 queries. Output reserve4096; nominal remaining space12k. Exact complete-chat token checks shrink only the new block.

* matching: up to48 matching/equality events (previous12),192 candidates considered.
* chains: up to24 chains (previous6),96 considered. Referenced matching events/formulas are necessary support, included in the same12k; no standalone matching list.
* non_inst_clauses: up to96 deduplicated clauses (previous24),256 considered. Generic hints are preserved as generic; no invented theory explanations.

These are ceilings, not guaranteed counts. No padding if evidence is missing. Existing compact event representation and relevance ranking retained. Initial advanced replay collected ONCE and packaged three ways. Subsequent replays follow the separate repaired candidate in each arm. Three arm order rotates by task to reduce fixed-order effects. No fourth control: comparison ranks block packages; it cannot establish an absolute gain over no advanced feedback.

Comparison includes cumulative success1/2/3, categories, pairwise exclusive IDs, exposure counts, tokens, context checks, truncation and missing tasks. Resume the same study with the same code/configuration; do not update a checkout while a study is running.

Update baseline/, diagnostics/, solver_needs_study/, configs/, prompts/, scripts/, tests/. GPU settings remain the tested64k L40S configuration (YaRN2, BF16, memory utilization0.95). No silent fallback.
