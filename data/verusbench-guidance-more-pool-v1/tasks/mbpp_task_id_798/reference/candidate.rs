use vstd::prelude::*;

fn main() {}

verus! {

spec fn sum_to(arr: Seq<i64>) -> int
    decreases arr.len(),
{
    if arr.len() == 0 {
        0
    } else {
        sum_to(arr.drop_last()) + arr.last()
    }
}

fn sum(arr: &Vec<i64>) -> (sum: i128)
    ensures
        sum_to(arr@) == sum,
{
    let mut index = 0;
    let mut sum = 0i128;

    while index < arr.len()
        invariant
            0 <= index <= arr.len(),
            sum == sum_to(arr@.subrange(0, index as int)),
            forall|j: int|
                0 <= j <= index ==> (i64::MIN * index <= (sum_to(#[trigger] arr@.subrange(0, j)))
                    <= i64::MAX * index),
{
        sum = sum + arr[index] as i128;
        index += 1;
    }
    sum
}

} // verus!