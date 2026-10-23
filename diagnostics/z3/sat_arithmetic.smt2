; Control for H => G: H is x >= 0 and G is x > 0.
; H AND NOT G is satisfiable, with the unique integer witness x = 0.
(set-logic QF_LIA)
(declare-const x Int)
(assert (>= x 0))
(assert (not (> x 0)))
(check-sat)
