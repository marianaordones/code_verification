(set-option :smt.mbqi false) (declare-fun f (Int) Int) (assert (forall ((x Int)) (! (> (f x) x) :pattern ((f x)) :qid user_candidate_unused))) (check-sat)
