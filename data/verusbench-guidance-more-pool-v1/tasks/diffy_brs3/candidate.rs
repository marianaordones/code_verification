use vstd::prelude::*;
fn main() {}
verus!{

pub fn myfun(a: &mut Vec<i32>, sum: &mut Vec<i32>, N: i32) 
	requires 
		old(a).len() == N,
		old(sum).len() == 1,
		N > 0,
		N < 1000,
	ensures
		sum[0] <= 3 * N,
{
	let mut i: usize = 0;
	while (i < N as usize)
		invariant 
			0 <= i <= N,
			a.len() == N,
			// Elements of a are set to 3 or 0 in this loop
			forall |k:int| 0 <= k < i ==> a[k] == 3 || a[k] == 0,
	{
		if (i % 3 == 0) {
			a.set(i, 3);
		} else {
			a.set(i, 0);
		}
		i = i + 1;
	}

	i = 0;
	
	while (i < N as usize)
		invariant 
			0 <= i <= N,
			a.len() == N,
			sum.len() == 1,
			// Elements of a are set to 3 or 0 in the first loop
			forall |k:int| 0 <= k < N ==> a[k] == 3 || a[k] == 0,
			// sum[0] is the sum of elements in a that are set to 3
			sum[0] == 3 * (i as i32) - a[0],
			N < 1000,
	{
		if (i == 0) {
			sum.set(0, 0);
		} else {
			sum.set(0, sum[0] + a[i]);
		}
		i = i + 1;
	}
}
}