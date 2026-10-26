(declare-fun f (Int) Int)
(assert (forall ((x Int)) (! (>= (f x) 0) :pattern ((f x)) :qid control_nonnegative)))
(assert (< (f 0) 0))
(check-sat)
