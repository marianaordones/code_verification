use vstd::prelude::*;

fn main() {}

verus! {

#[verifier::loop_isolation(false)]
fn min_second_value_first(arr: &Vec<Vec<i32>>) -> (first_of_min_second: i32)
    requires
        arr.len() > 0,
        forall|i: int| 0 <= i < arr.len() ==> #[trigger] arr[i].len() >= 2,
    ensures
        exists|i: int|
            0 <= i < arr.len() && first_of_min_second == #[trigger] arr[i][0] && (forall|j: int|
                0 <= j < arr.len() ==> (arr[i][1] <= #[trigger] arr[j][1])),
{
    let mut min_second_index = 0;
    let mut index = 0;

    while index < arr.len()
        invariant
            index <= arr.len(),
            min_second_index < arr.len(),
            forall|i: int| 0 <= i < index ==> arr[i][1] >= arr[min_second_index][1],
            forall|i: int| 0 <= i < arr.len() ==> arr[i].len() >= 2,
            arr.len() > 0,
    {
        if arr[index][1] < arr[min_second_index][1] {
            min_second_index = index;
        }
        index += 1;
    }
    arr[min_second_index][0]
}

} // verus!