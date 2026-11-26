#[allow(unused_imports)]
use vstd::prelude::*;
fn main() {}

verus! {
spec fn seq_to_set_rec<A>(seq: Seq<A>) -> Set<A>
    decreases seq.len()
{
    if seq.len() == 0 {
        Set::empty()
    } else {
        seq_to_set_rec(seq.drop_last()).insert(seq.last())
    }
}

fn remove_duplicates(nums: Vec<i32>) -> (res: Vec<i32>)
    ensures
        res@.no_duplicates(),
        nums@.to_set()==res@.to_set()
{
    let mut res = Vec::new();
    let mut i = 0;
    while i < nums.len()
        invariant
        0 <= i <= nums@.len(),
        nums@.subrange(0, i  as int).to_set() =~= (res@.to_set()),
        res@.no_duplicates(),
{
        let mut found = false;
        let mut j = 0;
        while j < res.len()
            invariant
            0 <= i < nums@.len(),
            0 <= j <= res@.len(),
            res@.no_duplicates(),
            nums@.subrange(0, i  as int).to_set() =~= (res@.to_set()),
            forall |k| 0 <= k < j ==> res@[k] != nums@[i as int],
        ensures
            0<= i < nums@.len(),
            0 <= j <= res@.len(),
            res@.no_duplicates(),
            nums@.subrange(0, i  as int).to_set() =~= (res@.to_set()),
            found ==> (j < res@.len() && res@[j as int] == nums@[i as int]),
            !found ==> forall |k| 0 <= k < j ==> res@[k] != nums@[i as int],
            !found ==> j == res@.len()
{
            if nums[i] == res[j] {
                found = true;
                break;
            }
            j += 1;
        }
        if !found {
            res.push(nums[i]);
        }
        i += 1;
    }
    res
}
}