use vstd::prelude::*;

fn main() {}

verus! {

fn has_common_element(list1: &Vec<i32>, list2: &Vec<i32>) -> (result: bool)
    ensures
        result == (exists|i: int, j: int|
            0 <= i < list1.len() && 0 <= j < list2.len() && (list1[i] == list2[j])),
{
    let mut i = 0;
    while i < list1.len()
        invariant
            0 <= i <= list1.len(),
            forall |k: int, l: int| 0 <= k < i && 0 <= l < list2.len() ==> list1[k] != list2[l],
    {
        let mut j = 0;
        while j < list2.len()
            invariant
                0 <= j <= list2.len(),
                0 <= i < list1.len(),
                forall |k: int| 0 <= k < j ==> list1[i] != list2[k],
        {
            if list1[i] == list2[j] {
                return true;
            }
            j += 1;
        }
        i += 1;
    }
    false
}

} // verus!