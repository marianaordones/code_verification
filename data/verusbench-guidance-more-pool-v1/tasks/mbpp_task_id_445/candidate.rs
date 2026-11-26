use vstd::prelude::*;

fn main() {}

verus! {

#[verifier::loop_isolation(false)]
fn element_wise_multiplication(arr1: &Vec<i32>, arr2: &Vec<i32>) -> (result: Vec<i32>)
    requires
        arr1.len() == arr2.len(),
        forall|i: int|
            (0 <= i < arr1.len()) ==> (i32::MIN <= #[trigger] (arr1[i] * arr2[i]) <= i32::MAX),
    ensures
        result.len() == arr1.len(),
        forall|i: int|
            0 <= i < result.len() ==> #[trigger] result[i] == #[trigger] (arr1[i] * arr2[i]),
{
    let mut output_arr = Vec::with_capacity(arr1.len());
    let mut index = 0;
    while index < arr1.len()
        invariant
            index <= arr1.len(),
            output_arr.len() == index,
            forall|i: int| 0 <= i < index ==> #[trigger] output_arr[i] == #[trigger] (arr1[i] * arr2[i]),
            arr1.len() == arr2.len(),
    {
        assert(0 <= index < arr1.len()); // Added by AI
        assert(i32::MIN <= #[trigger] (arr1[index] * arr2[index]) <= i32::MAX) by (nonlinear_arith)
            requires
                0 <= index < arr1.len(),
                forall|i: int|
                    (0 <= i < arr1.len()) ==> (i32::MIN <= #[trigger] (arr1[i] * arr2[i]) <= i32::MAX),
                {};
        output_arr.push((arr1[index] * arr2[index]));
        index += 1;
    }
    output_arr
}

} // verus!