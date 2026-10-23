# Lynette (MIT)

Vendored from Microsoft verus-proof-synthesis commit
`cbf9c0c6337b224fd8e5b7cb4e01ae65c0f98bc1`, `utils/lynette/source/`.
Sources and Cargo.lock are included to avoid downloading the full research repository
on the cluster. Parser dependency Verus revision is fixed by Cargo.lock.

Local change: `additions.rs` has three loops that returned success without checking
remaining candidate items. `scripts/prepare_lynette.py` patches these tails to allow
only proof/spec functions with bodies; extra exec functions, axioms and other items
are rejected. Existing termination and invariant-opening clauses are preserved
in signature comparisons (upstream erased these before comparing).
This patch must be tested on Linux with Cargo before scientific use.
The Python guard additionally preserves attributes, imports and non-Verus macros,
and rejects trusted/bypass constructs. No changes to proof search are reused.

Build: `cargo build --locked --release --manifest-path tools/lynette/source/Cargo.toml`.
