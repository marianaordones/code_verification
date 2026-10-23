// Deliberately false arithmetic obligation; a separate Verus control.
use vstd::prelude::*;
fn main() {}
verus! {
proof fn arithmetic_gap(x: int)
    requires x >= 0,
    ensures x > 0,
{
}
}
