#[allow(unused_imports)]
use vstd::prelude::*;

fn main() {}

verus! {

spec fn arith_sum_int(i: nat) -> nat
    decreases i
{
    if i == 0 { 0 } else { i + arith_sum_int( (i - 1) as nat) }
}

fn compute_arith_sum(n: u64) -> (sum: u64)
    requires
        arith_sum_int(n as nat) < 10000,
    ensures
        arith_sum_int(n as nat) == sum,
{
    let mut i: u64 = 0;
    let mut sum: u64 = 0;
    while i < n
        invariant
            0 <= i <= n,
            arith_sum_int(n as nat) < 10000,
            arith_sum_int(i as nat) == sum,
    {
        i = i + 1;
        assert(0 <= i * (i + 1) <= 10000) by (nonlinear_arith)
            requires
                0 <= i,
                i <= n,
                arith_sum_int(n as nat) < 10000,
                {};
        sum = sum + i;
    }
    sum
}

} // verus!