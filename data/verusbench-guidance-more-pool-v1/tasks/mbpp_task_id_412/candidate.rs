use vstd::prelude::*;

fn main() {}

verus! {

fn remove_odds(arr: &Vec<u32>) -> (even_list: Vec<u32>)
    ensures
        even_list@ == arr@.filter(|x: u32| x % 2 == 0),
{
    let mut even_list: Vec<u32> = Vec::new();
    let input_len = arr.len();

    let mut index = 0;
    while index < arr.len()
        invariant
            even_list.len() <= index,
            forall |i: int| 0 <= i < index ==> (even_list[( i ) as int] % 2 == 0),
            forall |i: int| 0 <= i < index ==> (arr[( i ) as int] % 2 == 0 ==> even_list[( i ) as int] == arr[( i ) as int]),
            forall |i: int| 0 <= i < arr.len() ==> (arr[( i ) as int] % 2 == 0) ==> (exists |j: int| 0 <= j < even_list.len() && even_list[( j ) as int] == arr[( i ) as int]),
            input_len == arr.len(),
    {
        if (arr[index] % 2 == 0) {
            even_list.push(arr[index]);
        }
        index += 1;
    }
    even_list
}

} // verus!