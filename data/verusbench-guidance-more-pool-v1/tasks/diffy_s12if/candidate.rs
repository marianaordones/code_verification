use vstd::prelude::*;
fn main() {}
verus!{
pub fn myfun(a: &mut Vec<i32>, sum: &mut Vec<i32>, N: usize)
	requires
		N > 0,
		old(a).len() == N,
		old(sum).len() == 1,
		N < 1000,
	ensures
		sum[0] == 2 * N,
{
	sum.set(0, 0);
	let mut i: usize = 0;
	while (i < N)
		invariant 
			0 <= i <= N,
			a.len() == N,
			sum.len() == 1,
			// All elements in a are still 0
			forall |k:int| 0 <= k < i ==> a[k] == 0,
	{
		a.set(i, 1);
		i = i + 1;
	}

	i = 0;
	while (i < N)
		invariant 
			0 <= i <= N,
			a.len() == N,
			sum.len() == 1,
			// All elements in a are either 1 or 2
			forall |k:int| 0 <= k < i ==> a[k] == 1 || a[k] == 2,
			// All elements in a that are 1 were set in this loop
			forall |k:int| 0 <= k < i && a[k] == 1 ==> a[k] == 1,
			// All elements in a that are 2 were set in this loop
			forall |k:int| 0 <= k < i && a[k] == 2 ==> a[k] == 2,
	{
		if (a[i] == 1) {
			a.set(i, a[i] + 1);
		} else {
			a.set(i, a[i] - 1);
		}
		i = i + 1;
	}

	i = 0;
	while (i < N)
		invariant 
			0 <= i <= N,
			a.len() == N,
			sum.len() == 1,
			sum[0] == 2 * i,
			// All elements in a are still 1 or 2
			forall |k:int| 0 <= k < N ==> a[k] == 1 || a[k] == 2,
			N < 1000,
	{
		if (a[i] == 2) {
			sum.set(0, sum[0] + a[i]);
		} else {
			sum.set(0, sum[0] * a[i]);
		}
		i = i + 1;
	}
}
}