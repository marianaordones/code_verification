// Deliberately false obligation for an extraction probe, not benchmark evidence.
use vstd::prelude::*;
fn main() {}
verus! {
proof fn missing_proof(a: Seq<int>)
    requires
        a.len() > 0,
        forall|j: int| 0 <= j < a.len() ==> #[trigger] a[j] >= 0,
    // Nonnegative elements need not be strictly positive: [0] is a witness.
    ensures a[0] > 0,
{
}
}
