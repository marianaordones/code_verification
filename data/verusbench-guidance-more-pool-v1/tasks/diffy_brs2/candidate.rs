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
		sum[0] <= 2 * N,
{
	let mut i: usize = 0;
	while (i < N as usize)
		invariant 
			0 <= i <= N,
			a.len() == N,
			sum.len() == 1,
			N > 0,
			N < 1000,
			forall |k: int| 0 <= k < i ==> (k % 2 == 0) ==> a[k] == 2,
			forall |k: int| 0 <= k < i ==> (k % 2 != 0) ==> a[k] == 0,
	{
		if (i % 2 == 0) {
			a.set(i, 2);
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
			N > 0,
			N < 1000,
			forall |k: int| 0 <= k < N ==> (k % 2 == 0) ==> a[k] == 2,
			forall |k: int| 0 <= k < N ==> (k % 2 != 0) ==> a[k] == 0,
			sum[0] <= 2 * i,
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