; Satisfiable quantified control without Verus's background axioms/options.
; f(x) = 0 for every integer x is one interpretation.
(set-logic AUFLIA)
(declare-fun f (Int) Int)
(assert (forall ((j Int)) (! (>= (f j) 0) :pattern ((f j)) :qid control_nonnegative)))
(assert (= (f 0) 0))
(check-sat)
