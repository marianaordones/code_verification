use vstd::prelude::*;

fn main() {}

verus! {

fn find_negative_numbers(arr: &Vec<i32>) -> (negative_list: Vec<i32>)
    ensures
        negative_list@ == arr@.filter(|x: i32| x < 0),
{
    let mut negative_list: Vec<i32> = Vec::new();
    let mut index = 0;
    while index < arr.len()
        invariant
            0 <= index <= arr.len(),
            negative_list.len() <= index,
            forall |k: int| 0 <= k < index ==> (negative_list@.contains(arr@[k]) ==> arr@[k] < 0),
            forall |k: int| 0 <= k < index ==> (arr@[k] < 0 ==> negative_list@.contains(arr@[k])),
    {
        if (arr[index] < 0) {
            negative_list.push(arr[index]);
        }
        index += 1;
    }
    negative_list
}

} // verus!