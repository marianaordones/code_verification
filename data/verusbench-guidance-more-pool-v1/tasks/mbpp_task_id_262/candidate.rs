use vstd::prelude::*;
fn main() {}

verus! {

fn split_array(list: &Vec<i32>, l: usize) -> (new_list: (Vec<i32>, Vec<i32>))
    requires
        list@.len() > 0,
        0 < l < list@.len(),
    ensures
        new_list.0@ == list@.subrange(0, l as int),
        new_list.1@ == list@.subrange(l as int, list.len() as int),
{
    let mut part1: Vec<i32> = Vec::new();
    let mut index = 0;
    while index < l
        invariant
            0 <= index <= l,
            part1.len() == index,
            forall |k: int| 0 <= k < index ==> part1[k as int] == list[k as int],
    {
        part1.push(list[index]);
        index += 1;
    }
    let mut part2: Vec<i32> = Vec::new();
    index = l;
    while index < list.len()
        invariant
            l <= index <= list.len(),
            part2.len() == index - l,
            forall |k: int| 0 <= k < part2.len() ==> part2[k as int] == list[(l + k) as int],
    {
        part2.push(list[index]);
        index += 1;
    }
    (part1, part2)
}

} // verus!