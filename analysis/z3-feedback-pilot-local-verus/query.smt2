(set-option :auto_config false)
(set-option :smt.mbqi false)
(set-option :smt.case_split 3)
(set-option :smt.qi.eager_threshold 100.0)
(set-option :smt.delay_units true)
(set-option :smt.arith.solver 2)
(set-option :smt.arith.nl false)
(set-option :pi.enabled false)
(set-option :rewriter.sort_disjunctions false)
(declare-sort %%Function%% 0)
(declare-sort FuelId 0)
(declare-sort Fuel 0)
(declare-const zero Fuel)
(declare-fun succ (Fuel) Fuel)
(declare-fun fuel_bool (FuelId) Bool)
(declare-fun fuel_bool_default (FuelId) Bool)
(declare-const fuel_defaults Bool)
(assert
 (=>
  fuel_defaults
  (forall ((id FuelId)) (!
    (= (fuel_bool id) (fuel_bool_default id))
    :pattern ((fuel_bool id))
    :qid prelude_fuel_defaults
    :skolemid skolem_prelude_fuel_defaults
))))
(declare-datatypes ((fndef 0)) (((fndef_singleton))))
(declare-sort Poly 0)
(declare-sort Height 0)
(declare-fun I (Int) Poly)
(declare-fun B (Bool) Poly)
(declare-fun R (Real) Poly)
(declare-fun F (fndef) Poly)
(declare-fun %I (Poly) Int)
(declare-fun %B (Poly) Bool)
(declare-fun %R (Poly) Real)
(declare-fun %F (Poly) fndef)
(declare-sort Type 0)
(declare-const BOOL Type)
(declare-const INT Type)
(declare-const NAT Type)
(declare-const REAL Type)
(declare-const CHAR Type)
(declare-const USIZE Type)
(declare-const ISIZE Type)
(declare-const TYPE%tuple%0. Type)
(declare-fun UINT (Int) Type)
(declare-fun SINT (Int) Type)
(declare-fun FLOAT (Int) Type)
(declare-fun CONST_INT (Int) Type)
(declare-fun CONST_BOOL (Bool) Type)
(declare-sort Dcr 0)
(declare-const $ Dcr)
(declare-const $slice Dcr)
(declare-const $dyn Dcr)
(declare-fun DST (Dcr) Dcr)
(declare-fun REF (Dcr) Dcr)
(declare-fun MUT_REF (Dcr) Dcr)
(declare-fun BOX (Dcr Type Dcr) Dcr)
(declare-fun RC (Dcr Type Dcr) Dcr)
(declare-fun ARC (Dcr Type Dcr) Dcr)
(declare-fun GHOST (Dcr) Dcr)
(declare-fun TRACKED (Dcr) Dcr)
(declare-fun NEVER (Dcr) Dcr)
(declare-fun CONST_PTR (Dcr) Dcr)
(declare-fun ARRAY (Dcr Type Dcr Type) Type)
(declare-fun MUTREF (Dcr Type) Type)
(declare-fun SLICE (Dcr Type) Type)
(declare-const STRSLICE Type)
(declare-const ALLOCATOR_GLOBAL Type)
(declare-fun PTR (Dcr Type) Type)
(declare-fun has_type (Poly Type) Bool)
(declare-fun sized (Dcr) Bool)
(declare-fun as_type (Poly Type) Poly)
(declare-fun mk_fun (%%Function%%) %%Function%%)
(declare-fun const_int (Type) Int)
(declare-fun const_bool (Type) Bool)
(declare-fun mut_ref_current% (Poly) Poly)
(declare-fun mut_ref_future% (Poly) Poly)
(declare-fun mut_ref_update_current% (Poly Poly) Poly)
(assert
 (forall ((m Poly) (arg Poly)) (!
   (= (mut_ref_current% (mut_ref_update_current% m arg)) arg)
   :pattern ((mut_ref_update_current% m arg))
   :qid prelude_mut_ref_update_current_current
   :skolemid skolem_prelude_mut_ref_update_current_current
)))
(assert
 (forall ((m Poly) (arg Poly)) (!
   (= (mut_ref_future% (mut_ref_update_current% m arg)) (mut_ref_future% m))
   :pattern ((mut_ref_update_current% m arg))
   :qid prelude_mut_ref_update_current_future
   :skolemid skolem_prelude_mut_ref_update_current_future
)))
(assert
 (forall ((m Poly) (d Dcr) (t Type)) (!
   (=>
    (has_type m (MUTREF d t))
    (has_type (mut_ref_current% m) t)
   )
   :pattern ((has_type m (MUTREF d t)) (mut_ref_current% m))
   :qid prelude_mut_ref_current_has_type
   :skolemid skolem_prelude_mut_ref_current_has_type
)))
(assert
 (forall ((m Poly) (d Dcr) (t Type)) (!
   (=>
    (has_type m (MUTREF d t))
    (has_type (mut_ref_future% m) t)
   )
   :pattern ((has_type m (MUTREF d t)) (mut_ref_future% m))
   :qid prelude_mut_ref_current_has_type
   :skolemid skolem_prelude_mut_ref_current_has_type
)))
(assert
 (forall ((m Poly) (d Dcr) (t Type) (arg Poly)) (!
   (=>
    (and
     (has_type m (MUTREF d t))
     (has_type arg t)
    )
    (has_type (mut_ref_update_current% m arg) (MUTREF d t))
   )
   :pattern ((has_type m (MUTREF d t)) (mut_ref_update_current% m arg))
   :qid prelude_mut_ref_update_has_type
   :skolemid skolem_prelude_mut_ref_update_has_type
)))
(assert
 (forall ((d Dcr)) (!
   (=>
    (sized d)
    (sized (DST d))
   )
   :pattern ((sized (DST d)))
   :qid prelude_sized_decorate_struct_inherit
   :skolemid skolem_prelude_sized_decorate_struct_inherit
)))
(assert
 (forall ((d Dcr)) (!
   (sized (REF d))
   :pattern ((sized (REF d)))
   :qid prelude_sized_decorate_ref
   :skolemid skolem_prelude_sized_decorate_ref
)))
(assert
 (forall ((d Dcr)) (!
   (sized (MUT_REF d))
   :pattern ((sized (MUT_REF d)))
   :qid prelude_sized_decorate_mut_ref
   :skolemid skolem_prelude_sized_decorate_mut_ref
)))
(assert
 (forall ((d Dcr) (t Type) (d2 Dcr)) (!
   (sized (BOX d t d2))
   :pattern ((sized (BOX d t d2)))
   :qid prelude_sized_decorate_box
   :skolemid skolem_prelude_sized_decorate_box
)))
(assert
 (forall ((d Dcr) (t Type) (d2 Dcr)) (!
   (sized (RC d t d2))
   :pattern ((sized (RC d t d2)))
   :qid prelude_sized_decorate_rc
   :skolemid skolem_prelude_sized_decorate_rc
)))
(assert
 (forall ((d Dcr) (t Type) (d2 Dcr)) (!
   (sized (ARC d t d2))
   :pattern ((sized (ARC d t d2)))
   :qid prelude_sized_decorate_arc
   :skolemid skolem_prelude_sized_decorate_arc
)))
(assert
 (forall ((d Dcr)) (!
   (sized (GHOST d))
   :pattern ((sized (GHOST d)))
   :qid prelude_sized_decorate_ghost
   :skolemid skolem_prelude_sized_decorate_ghost
)))
(assert
 (forall ((d Dcr)) (!
   (sized (TRACKED d))
   :pattern ((sized (TRACKED d)))
   :qid prelude_sized_decorate_tracked
   :skolemid skolem_prelude_sized_decorate_tracked
)))
(assert
 (forall ((d Dcr)) (!
   (sized (NEVER d))
   :pattern ((sized (NEVER d)))
   :qid prelude_sized_decorate_never
   :skolemid skolem_prelude_sized_decorate_never
)))
(assert
 (forall ((d Dcr)) (!
   (sized (CONST_PTR d))
   :pattern ((sized (CONST_PTR d)))
   :qid prelude_sized_decorate_const_ptr
   :skolemid skolem_prelude_sized_decorate_const_ptr
)))
(assert
 (sized $)
)
(assert
 (forall ((i Int)) (!
   (= i (const_int (CONST_INT i)))
   :pattern ((CONST_INT i))
   :qid prelude_type_id_const_int
   :skolemid skolem_prelude_type_id_const_int
)))
(assert
 (forall ((b Bool)) (!
   (= b (const_bool (CONST_BOOL b)))
   :pattern ((CONST_BOOL b))
   :qid prelude_type_id_const_bool
   :skolemid skolem_prelude_type_id_const_bool
)))
(assert
 (forall ((b Bool)) (!
   (has_type (B b) BOOL)
   :pattern ((has_type (B b) BOOL))
   :qid prelude_has_type_bool
   :skolemid skolem_prelude_has_type_bool
)))
(assert
 (forall ((r Real)) (!
   (has_type (R r) REAL)
   :pattern ((has_type (R r) REAL))
   :qid prelude_has_type_real
   :skolemid skolem_prelude_has_type_real
)))
(assert
 (forall ((x Poly) (t Type)) (!
   (and
    (has_type (as_type x t) t)
    (=>
     (has_type x t)
     (= x (as_type x t))
   ))
   :pattern ((as_type x t))
   :qid prelude_as_type
   :skolemid skolem_prelude_as_type
)))
(assert
 (forall ((x %%Function%%)) (!
   (= (mk_fun x) x)
   :pattern ((mk_fun x))
   :qid prelude_mk_fun
   :skolemid skolem_prelude_mk_fun
)))
(assert
 (forall ((x Bool)) (!
   (= x (%B (B x)))
   :pattern ((B x))
   :qid prelude_unbox_box_bool
   :skolemid skolem_prelude_unbox_box_bool
)))
(assert
 (forall ((x Int)) (!
   (= x (%I (I x)))
   :pattern ((I x))
   :qid prelude_unbox_box_int
   :skolemid skolem_prelude_unbox_box_int
)))
(assert
 (forall ((x Real)) (!
   (= x (%R (R x)))
   :pattern ((R x))
   :qid prelude_unbox_box_real
   :skolemid skolem_prelude_unbox_box_real
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x BOOL)
    (= x (B (%B x)))
   )
   :pattern ((has_type x BOOL))
   :qid prelude_box_unbox_bool
   :skolemid skolem_prelude_box_unbox_bool
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x INT)
    (= x (I (%I x)))
   )
   :pattern ((has_type x INT))
   :qid prelude_box_unbox_int
   :skolemid skolem_prelude_box_unbox_int
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x NAT)
    (= x (I (%I x)))
   )
   :pattern ((has_type x NAT))
   :qid prelude_box_unbox_nat
   :skolemid skolem_prelude_box_unbox_nat
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x USIZE)
    (= x (I (%I x)))
   )
   :pattern ((has_type x USIZE))
   :qid prelude_box_unbox_usize
   :skolemid skolem_prelude_box_unbox_usize
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x ISIZE)
    (= x (I (%I x)))
   )
   :pattern ((has_type x ISIZE))
   :qid prelude_box_unbox_isize
   :skolemid skolem_prelude_box_unbox_isize
)))
(assert
 (forall ((bits Int) (x Poly)) (!
   (=>
    (has_type x (UINT bits))
    (= x (I (%I x)))
   )
   :pattern ((has_type x (UINT bits)))
   :qid prelude_box_unbox_uint
   :skolemid skolem_prelude_box_unbox_uint
)))
(assert
 (forall ((bits Int) (x Poly)) (!
   (=>
    (has_type x (SINT bits))
    (= x (I (%I x)))
   )
   :pattern ((has_type x (SINT bits)))
   :qid prelude_box_unbox_sint
   :skolemid skolem_prelude_box_unbox_sint
)))
(assert
 (forall ((bits Int) (x Poly)) (!
   (=>
    (has_type x (FLOAT bits))
    (= x (I (%I x)))
   )
   :pattern ((has_type x (FLOAT bits)))
   :qid prelude_box_unbox_sint
   :skolemid skolem_prelude_box_unbox_sint
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x CHAR)
    (= x (I (%I x)))
   )
   :pattern ((has_type x CHAR))
   :qid prelude_box_unbox_char
   :skolemid skolem_prelude_box_unbox_char
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x REAL)
    (= x (R (%R x)))
   )
   :pattern ((has_type x REAL))
   :qid prelude_box_unbox_real
   :skolemid skolem_prelude_box_unbox_real
)))
(declare-fun ext_eq (Bool Type Poly Poly) Bool)
(assert
 (forall ((deep Bool) (t Type) (x Poly) (y Poly)) (!
   (= (= x y) (ext_eq deep t x y))
   :pattern ((ext_eq deep t x y))
   :qid prelude_ext_eq
   :skolemid skolem_prelude_ext_eq
)))
(declare-const SZ Int)
(assert
 (or
  (= SZ 32)
  (= SZ 64)
))
(declare-fun uHi (Int) Int)
(declare-fun iLo (Int) Int)
(declare-fun iHi (Int) Int)
(assert
 (= (uHi 8) 256)
)
(assert
 (= (uHi 16) 65536)
)
(assert
 (= (uHi 32) 4294967296)
)
(assert
 (= (uHi 64) 18446744073709551616)
)
(assert
 (= (uHi 128) (+ 1 340282366920938463463374607431768211455))
)
(assert
 (= (iLo 8) (- 128))
)
(assert
 (= (iLo 16) (- 32768))
)
(assert
 (= (iLo 32) (- 2147483648))
)
(assert
 (= (iLo 64) (- 9223372036854775808))
)
(assert
 (= (iLo 128) (- 170141183460469231731687303715884105728))
)
(assert
 (= (iHi 8) 128)
)
(assert
 (= (iHi 16) 32768)
)
(assert
 (= (iHi 32) 2147483648)
)
(assert
 (= (iHi 64) 9223372036854775808)
)
(assert
 (= (iHi 128) 170141183460469231731687303715884105728)
)
(declare-fun nClip (Int) Int)
(declare-fun uClip (Int Int) Int)
(declare-fun iClip (Int Int) Int)
(declare-fun charClip (Int) Int)
(assert
 (forall ((i Int)) (!
   (and
    (<= 0 (nClip i))
    (=>
     (<= 0 i)
     (= i (nClip i))
   ))
   :pattern ((nClip i))
   :qid prelude_nat_clip
   :skolemid skolem_prelude_nat_clip
)))
(assert
 (forall ((bits Int) (i Int)) (!
   (and
    (<= 0 (uClip bits i))
    (< (uClip bits i) (uHi bits))
    (=>
     (and
      (<= 0 i)
      (< i (uHi bits))
     )
     (= i (uClip bits i))
   ))
   :pattern ((uClip bits i))
   :qid prelude_u_clip
   :skolemid skolem_prelude_u_clip
)))
(assert
 (forall ((bits Int) (i Int)) (!
   (and
    (<= (iLo bits) (iClip bits i))
    (< (iClip bits i) (iHi bits))
    (=>
     (and
      (<= (iLo bits) i)
      (< i (iHi bits))
     )
     (= i (iClip bits i))
   ))
   :pattern ((iClip bits i))
   :qid prelude_i_clip
   :skolemid skolem_prelude_i_clip
)))
(assert
 (forall ((i Int)) (!
   (and
    (or
     (and
      (<= 0 (charClip i))
      (<= (charClip i) 55295)
     )
     (and
      (<= 57344 (charClip i))
      (<= (charClip i) 1114111)
    ))
    (=>
     (or
      (and
       (<= 0 i)
       (<= i 55295)
      )
      (and
       (<= 57344 i)
       (<= i 1114111)
     ))
     (= i (charClip i))
   ))
   :pattern ((charClip i))
   :qid prelude_char_clip
   :skolemid skolem_prelude_char_clip
)))
(declare-fun uInv (Int Int) Bool)
(declare-fun iInv (Int Int) Bool)
(declare-fun charInv (Int) Bool)
(assert
 (forall ((bits Int) (i Int)) (!
   (= (uInv bits i) (and
     (<= 0 i)
     (< i (uHi bits))
   ))
   :pattern ((uInv bits i))
   :qid prelude_u_inv
   :skolemid skolem_prelude_u_inv
)))
(assert
 (forall ((bits Int) (i Int)) (!
   (= (iInv bits i) (and
     (<= (iLo bits) i)
     (< i (iHi bits))
   ))
   :pattern ((iInv bits i))
   :qid prelude_i_inv
   :skolemid skolem_prelude_i_inv
)))
(assert
 (forall ((i Int)) (!
   (= (charInv i) (or
     (and
      (<= 0 i)
      (<= i 55295)
     )
     (and
      (<= 57344 i)
      (<= i 1114111)
   )))
   :pattern ((charInv i))
   :qid prelude_char_inv
   :skolemid skolem_prelude_char_inv
)))
(assert
 (forall ((x Int)) (!
   (has_type (I x) INT)
   :pattern ((has_type (I x) INT))
   :qid prelude_has_type_int
   :skolemid skolem_prelude_has_type_int
)))
(assert
 (forall ((x Int)) (!
   (=>
    (<= 0 x)
    (has_type (I x) NAT)
   )
   :pattern ((has_type (I x) NAT))
   :qid prelude_has_type_nat
   :skolemid skolem_prelude_has_type_nat
)))
(assert
 (forall ((x Int)) (!
   (=>
    (uInv SZ x)
    (has_type (I x) USIZE)
   )
   :pattern ((has_type (I x) USIZE))
   :qid prelude_has_type_usize
   :skolemid skolem_prelude_has_type_usize
)))
(assert
 (forall ((x Int)) (!
   (=>
    (iInv SZ x)
    (has_type (I x) ISIZE)
   )
   :pattern ((has_type (I x) ISIZE))
   :qid prelude_has_type_isize
   :skolemid skolem_prelude_has_type_isize
)))
(assert
 (forall ((bits Int) (x Int)) (!
   (=>
    (uInv bits x)
    (has_type (I x) (UINT bits))
   )
   :pattern ((has_type (I x) (UINT bits)))
   :qid prelude_has_type_uint
   :skolemid skolem_prelude_has_type_uint
)))
(assert
 (forall ((bits Int) (x Int)) (!
   (=>
    (iInv bits x)
    (has_type (I x) (SINT bits))
   )
   :pattern ((has_type (I x) (SINT bits)))
   :qid prelude_has_type_sint
   :skolemid skolem_prelude_has_type_sint
)))
(assert
 (forall ((bits Int) (x Int)) (!
   (=>
    (uInv bits x)
    (has_type (I x) (FLOAT bits))
   )
   :pattern ((has_type (I x) (FLOAT bits)))
   :qid prelude_has_type_sint
   :skolemid skolem_prelude_has_type_sint
)))
(assert
 (forall ((x Int)) (!
   (=>
    (charInv x)
    (has_type (I x) CHAR)
   )
   :pattern ((has_type (I x) CHAR))
   :qid prelude_has_type_char
   :skolemid skolem_prelude_has_type_char
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x NAT)
    (<= 0 (%I x))
   )
   :pattern ((has_type x NAT))
   :qid prelude_unbox_int
   :skolemid skolem_prelude_unbox_int
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x USIZE)
    (uInv SZ (%I x))
   )
   :pattern ((has_type x USIZE))
   :qid prelude_unbox_usize
   :skolemid skolem_prelude_unbox_usize
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x ISIZE)
    (iInv SZ (%I x))
   )
   :pattern ((has_type x ISIZE))
   :qid prelude_unbox_isize
   :skolemid skolem_prelude_unbox_isize
)))
(assert
 (forall ((bits Int) (x Poly)) (!
   (=>
    (has_type x (UINT bits))
    (uInv bits (%I x))
   )
   :pattern ((has_type x (UINT bits)))
   :qid prelude_unbox_uint
   :skolemid skolem_prelude_unbox_uint
)))
(assert
 (forall ((bits Int) (x Poly)) (!
   (=>
    (has_type x (SINT bits))
    (iInv bits (%I x))
   )
   :pattern ((has_type x (SINT bits)))
   :qid prelude_unbox_sint
   :skolemid skolem_prelude_unbox_sint
)))
(assert
 (forall ((bits Int) (x Poly)) (!
   (=>
    (has_type x (FLOAT bits))
    (uInv bits (%I x))
   )
   :pattern ((has_type x (FLOAT bits)))
   :qid prelude_unbox_sint
   :skolemid skolem_prelude_unbox_sint
)))
(declare-fun Add (Int Int) Int)
(declare-fun Sub (Int Int) Int)
(declare-fun Mul (Int Int) Int)
(declare-fun EucDiv (Int Int) Int)
(declare-fun EucMod (Int Int) Int)
(declare-fun RAdd (Real Real) Real)
(declare-fun RSub (Real Real) Real)
(declare-fun RMul (Real Real) Real)
(declare-fun RDiv (Real Real) Real)
(assert
 (forall ((x Int) (y Int)) (!
   (= (Add x y) (+ x y))
   :pattern ((Add x y))
   :qid prelude_add
   :skolemid skolem_prelude_add
)))
(assert
 (forall ((x Int) (y Int)) (!
   (= (Sub x y) (- x y))
   :pattern ((Sub x y))
   :qid prelude_sub
   :skolemid skolem_prelude_sub
)))
(assert
 (forall ((x Int) (y Int)) (!
   (= (Mul x y) (* x y))
   :pattern ((Mul x y))
   :qid prelude_mul
   :skolemid skolem_prelude_mul
)))
(assert
 (forall ((x Int) (y Int)) (!
   (= (EucDiv x y) (div x y))
   :pattern ((EucDiv x y))
   :qid prelude_eucdiv
   :skolemid skolem_prelude_eucdiv
)))
(assert
 (forall ((x Int) (y Int)) (!
   (= (EucMod x y) (mod x y))
   :pattern ((EucMod x y))
   :qid prelude_eucmod
   :skolemid skolem_prelude_eucmod
)))
(assert
 (forall ((x Real) (y Real)) (!
   (= (RAdd x y) (+ x y))
   :pattern ((RAdd x y))
   :qid prelude_radd
   :skolemid skolem_prelude_radd
)))
(assert
 (forall ((x Real) (y Real)) (!
   (= (RSub x y) (- x y))
   :pattern ((RSub x y))
   :qid prelude_rsub
   :skolemid skolem_prelude_rsub
)))
(assert
 (forall ((x Real) (y Real)) (!
   (= (RMul x y) (* x y))
   :pattern ((RMul x y))
   :qid prelude_rmul
   :skolemid skolem_prelude_rmul
)))
(assert
 (forall ((x Real) (y Real)) (!
   (= (RDiv x y) (/ x y))
   :pattern ((RDiv x y))
   :qid prelude_rdiv
   :skolemid skolem_prelude_rdiv
)))
(assert
 (forall ((x Int) (y Int)) (!
   (=>
    (and
     (<= 0 x)
     (<= 0 y)
    )
    (<= 0 (Mul x y))
   )
   :pattern ((Mul x y))
   :qid prelude_mul_nats
   :skolemid skolem_prelude_mul_nats
)))
(assert
 (forall ((x Int) (y Int)) (!
   (=>
    (and
     (<= 0 x)
     (< 0 y)
    )
    (and
     (<= 0 (EucDiv x y))
     (<= (EucDiv x y) x)
   ))
   :pattern ((EucDiv x y))
   :qid prelude_div_unsigned_in_bounds
   :skolemid skolem_prelude_div_unsigned_in_bounds
)))
(assert
 (forall ((x Int) (y Int)) (!
   (=>
    (and
     (<= 0 x)
     (< 0 y)
    )
    (and
     (<= 0 (EucMod x y))
     (< (EucMod x y) y)
   ))
   :pattern ((EucMod x y))
   :qid prelude_mod_unsigned_in_bounds
   :skolemid skolem_prelude_mod_unsigned_in_bounds
)))
(declare-fun bitxor (Poly Poly) Int)
(declare-fun bitand (Poly Poly) Int)
(declare-fun bitor (Poly Poly) Int)
(declare-fun bitshr (Poly Poly) Int)
(declare-fun bitshl (Poly Poly) Int)
(declare-fun bitnot (Poly) Int)
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (uInv bits (%I x))
     (uInv bits (%I y))
    )
    (uInv bits (bitxor x y))
   )
   :pattern ((uClip bits (bitxor x y)))
   :qid prelude_bit_xor_u_inv
   :skolemid skolem_prelude_bit_xor_u_inv
)))
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (iInv bits (%I x))
     (iInv bits (%I y))
    )
    (iInv bits (bitxor x y))
   )
   :pattern ((iClip bits (bitxor x y)))
   :qid prelude_bit_xor_i_inv
   :skolemid skolem_prelude_bit_xor_i_inv
)))
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (uInv bits (%I x))
     (uInv bits (%I y))
    )
    (uInv bits (bitor x y))
   )
   :pattern ((uClip bits (bitor x y)))
   :qid prelude_bit_or_u_inv
   :skolemid skolem_prelude_bit_or_u_inv
)))
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (iInv bits (%I x))
     (iInv bits (%I y))
    )
    (iInv bits (bitor x y))
   )
   :pattern ((iClip bits (bitor x y)))
   :qid prelude_bit_or_i_inv
   :skolemid skolem_prelude_bit_or_i_inv
)))
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (uInv bits (%I x))
     (uInv bits (%I y))
    )
    (uInv bits (bitand x y))
   )
   :pattern ((uClip bits (bitand x y)))
   :qid prelude_bit_and_u_inv
   :skolemid skolem_prelude_bit_and_u_inv
)))
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (iInv bits (%I x))
     (iInv bits (%I y))
    )
    (iInv bits (bitand x y))
   )
   :pattern ((iClip bits (bitand x y)))
   :qid prelude_bit_and_i_inv
   :skolemid skolem_prelude_bit_and_i_inv
)))
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (uInv bits (%I x))
     (<= 0 (%I y))
    )
    (uInv bits (bitshr x y))
   )
   :pattern ((uClip bits (bitshr x y)))
   :qid prelude_bit_shr_u_inv
   :skolemid skolem_prelude_bit_shr_u_inv
)))
(assert
 (forall ((x Poly) (y Poly) (bits Int)) (!
   (=>
    (and
     (iInv bits (%I x))
     (<= 0 (%I y))
    )
    (iInv bits (bitshr x y))
   )
   :pattern ((iClip bits (bitshr x y)))
   :qid prelude_bit_shr_i_inv
   :skolemid skolem_prelude_bit_shr_i_inv
)))
(declare-fun singular_mod (Int Int) Int)
(assert
 (forall ((x Int) (y Int)) (!
   (=>
    (not (= y 0))
    (= (EucMod x y) (singular_mod x y))
   )
   :pattern ((singular_mod x y))
   :qid prelude_singularmod
   :skolemid skolem_prelude_singularmod
)))
(declare-fun has_resolved (Dcr Type Poly) Bool)
(declare-fun closure_req (Type Dcr Type Poly Poly) Bool)
(declare-fun closure_ens (Type Dcr Type Poly Poly Poly) Bool)
(declare-fun default_ens (Type Dcr Type Poly Poly Poly) Bool)
(declare-fun height (Poly) Height)
(declare-fun height_lt (Height Height) Bool)
(declare-fun fun_from_recursive_field (Poly) Poly)
(declare-fun check_decrease_int (Int Int Bool) Bool)
(assert
 (forall ((cur Int) (prev Int) (otherwise Bool)) (!
   (= (check_decrease_int cur prev otherwise) (or
     (and
      (<= 0 cur)
      (< cur prev)
     )
     (and
      (= cur prev)
      otherwise
   )))
   :pattern ((check_decrease_int cur prev otherwise))
   :qid prelude_check_decrease_int
   :skolemid skolem_prelude_check_decrease_int
)))
(declare-fun check_decrease_height (Poly Poly Bool) Bool)
(assert
 (forall ((cur Poly) (prev Poly) (otherwise Bool)) (!
   (= (check_decrease_height cur prev otherwise) (or
     (height_lt (height cur) (height prev))
     (and
      (= (height cur) (height prev))
      otherwise
   )))
   :pattern ((check_decrease_height cur prev otherwise))
   :qid prelude_check_decrease_height
   :skolemid skolem_prelude_check_decrease_height
)))
(assert
 (forall ((x Height) (y Height)) (!
   (= (height_lt x y) (and
     ((_ partial-order 0) x y)
     (not (= x y))
   ))
   :pattern ((height_lt x y))
   :qid prelude_height_lt
   :skolemid skolem_prelude_height_lt
)))
(declare-const fuel%vstd!std_specs.ops.impl&%77.obeys_div_spec. FuelId)
(declare-const fuel%vstd!std_specs.ops.impl&%77.div_req. FuelId)
(declare-const fuel%vstd!std_specs.ops.impl&%77.div_spec. FuelId)
(declare-const fuel%candidate!min_val. FuelId)
(declare-const fuel%candidate!candies_after_division. FuelId)
(declare-const fuel%candidate!is_achievable. FuelId)
(declare-const fuel%candidate!is_optimal. FuelId)
(declare-const fuel%vstd!array.group_array_axioms. FuelId)
(declare-const fuel%vstd!function.group_function_axioms. FuelId)
(declare-const fuel%vstd!laws_cmp.group_laws_cmp. FuelId)
(declare-const fuel%vstd!laws_eq.bool_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.u8_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.i8_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.u16_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.i16_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.u32_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.i32_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.u64_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.i64_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.u128_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.i128_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.usize_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.isize_laws.group_laws_eq. FuelId)
(declare-const fuel%vstd!laws_eq.group_laws_eq. FuelId)
(declare-const fuel%vstd!layout.group_align_properties. FuelId)
(declare-const fuel%vstd!layout.group_layout_axioms. FuelId)
(declare-const fuel%vstd!map.group_map_axioms. FuelId)
(declare-const fuel%vstd!multiset.group_multiset_axioms. FuelId)
(declare-const fuel%vstd!raw_ptr.group_raw_ptr_axioms. FuelId)
(declare-const fuel%vstd!seq.group_seq_axioms. FuelId)
(declare-const fuel%vstd!seq_lib.group_filter_ensures. FuelId)
(declare-const fuel%vstd!seq_lib.group_seq_lib_default. FuelId)
(declare-const fuel%vstd!set.group_set_axioms. FuelId)
(declare-const fuel%vstd!set_lib.group_set_lib_default. FuelId)
(declare-const fuel%vstd!slice.group_slice_axioms. FuelId)
(declare-const fuel%vstd!string.group_string_axioms. FuelId)
(declare-const fuel%vstd!std_specs.bits.group_bits_axioms. FuelId)
(declare-const fuel%vstd!std_specs.control_flow.group_control_flow_axioms. FuelId)
(declare-const fuel%vstd!std_specs.manually_drop.group_manually_drop_axioms. FuelId)
(declare-const fuel%vstd!std_specs.hash.group_hash_axioms. FuelId)
(declare-const fuel%vstd!std_specs.range.group_range_axioms. FuelId)
(declare-const fuel%vstd!std_specs.slice.group_slice_axioms. FuelId)
(declare-const fuel%vstd!std_specs.vec.group_vec_axioms. FuelId)
(declare-const fuel%vstd!std_specs.vecdeque.group_vec_dequeue_axioms. FuelId)
(declare-const fuel%vstd!group_vstd_default. FuelId)
(assert
 (distinct fuel%vstd!std_specs.ops.impl&%77.obeys_div_spec. fuel%vstd!std_specs.ops.impl&%77.div_req.
  fuel%vstd!std_specs.ops.impl&%77.div_spec. fuel%candidate!min_val. fuel%candidate!candies_after_division.
  fuel%candidate!is_achievable. fuel%candidate!is_optimal. fuel%vstd!array.group_array_axioms.
  fuel%vstd!function.group_function_axioms. fuel%vstd!laws_cmp.group_laws_cmp. fuel%vstd!laws_eq.bool_laws.group_laws_eq.
  fuel%vstd!laws_eq.u8_laws.group_laws_eq. fuel%vstd!laws_eq.i8_laws.group_laws_eq.
  fuel%vstd!laws_eq.u16_laws.group_laws_eq. fuel%vstd!laws_eq.i16_laws.group_laws_eq.
  fuel%vstd!laws_eq.u32_laws.group_laws_eq. fuel%vstd!laws_eq.i32_laws.group_laws_eq.
  fuel%vstd!laws_eq.u64_laws.group_laws_eq. fuel%vstd!laws_eq.i64_laws.group_laws_eq.
  fuel%vstd!laws_eq.u128_laws.group_laws_eq. fuel%vstd!laws_eq.i128_laws.group_laws_eq.
  fuel%vstd!laws_eq.usize_laws.group_laws_eq. fuel%vstd!laws_eq.isize_laws.group_laws_eq.
  fuel%vstd!laws_eq.group_laws_eq. fuel%vstd!layout.group_align_properties. fuel%vstd!layout.group_layout_axioms.
  fuel%vstd!map.group_map_axioms. fuel%vstd!multiset.group_multiset_axioms. fuel%vstd!raw_ptr.group_raw_ptr_axioms.
  fuel%vstd!seq.group_seq_axioms. fuel%vstd!seq_lib.group_filter_ensures. fuel%vstd!seq_lib.group_seq_lib_default.
  fuel%vstd!set.group_set_axioms. fuel%vstd!set_lib.group_set_lib_default. fuel%vstd!slice.group_slice_axioms.
  fuel%vstd!string.group_string_axioms. fuel%vstd!std_specs.bits.group_bits_axioms.
  fuel%vstd!std_specs.control_flow.group_control_flow_axioms. fuel%vstd!std_specs.manually_drop.group_manually_drop_axioms.
  fuel%vstd!std_specs.hash.group_hash_axioms. fuel%vstd!std_specs.range.group_range_axioms.
  fuel%vstd!std_specs.slice.group_slice_axioms. fuel%vstd!std_specs.vec.group_vec_axioms.
  fuel%vstd!std_specs.vecdeque.group_vec_dequeue_axioms. fuel%vstd!group_vstd_default.
))
(assert
 (=>
  (fuel_bool_default fuel%vstd!laws_eq.group_laws_eq.)
  (and
   (fuel_bool_default fuel%vstd!laws_eq.bool_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.u8_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.i8_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.u16_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.i16_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.u32_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.i32_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.u64_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.i64_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.u128_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.i128_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.usize_laws.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_eq.isize_laws.group_laws_eq.)
)))
(assert
 (=>
  (fuel_bool_default fuel%vstd!layout.group_layout_axioms.)
  (fuel_bool_default fuel%vstd!layout.group_align_properties.)
))
(assert
 (=>
  (fuel_bool_default fuel%vstd!seq_lib.group_seq_lib_default.)
  (fuel_bool_default fuel%vstd!seq_lib.group_filter_ensures.)
))
(assert
 (fuel_bool_default fuel%vstd!group_vstd_default.)
)
(assert
 (=>
  (fuel_bool_default fuel%vstd!group_vstd_default.)
  (and
   (fuel_bool_default fuel%vstd!seq.group_seq_axioms.)
   (fuel_bool_default fuel%vstd!seq_lib.group_seq_lib_default.)
   (fuel_bool_default fuel%vstd!map.group_map_axioms.)
   (fuel_bool_default fuel%vstd!set.group_set_axioms.)
   (fuel_bool_default fuel%vstd!set_lib.group_set_lib_default.)
   (fuel_bool_default fuel%vstd!multiset.group_multiset_axioms.)
   (fuel_bool_default fuel%vstd!function.group_function_axioms.)
   (fuel_bool_default fuel%vstd!laws_eq.group_laws_eq.)
   (fuel_bool_default fuel%vstd!laws_cmp.group_laws_cmp.)
   (fuel_bool_default fuel%vstd!slice.group_slice_axioms.)
   (fuel_bool_default fuel%vstd!array.group_array_axioms.)
   (fuel_bool_default fuel%vstd!string.group_string_axioms.)
   (fuel_bool_default fuel%vstd!raw_ptr.group_raw_ptr_axioms.)
   (fuel_bool_default fuel%vstd!layout.group_layout_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.range.group_range_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.bits.group_bits_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.control_flow.group_control_flow_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.slice.group_slice_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.manually_drop.group_manually_drop_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.vec.group_vec_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.vecdeque.group_vec_dequeue_axioms.)
   (fuel_bool_default fuel%vstd!std_specs.hash.group_hash_axioms.)
)))
(declare-fun tr_bound%core!ops.arith.Div. (Dcr Type Dcr Type) Bool)
(declare-fun tr_bound%vstd!std_specs.ops.DivSpec. (Dcr Type Dcr Type) Bool)
(declare-fun proj%%core!ops.arith.Div./Output (Dcr Type Dcr Type) Dcr)
(declare-fun proj%core!ops.arith.Div./Output (Dcr Type Dcr Type) Type)
(declare-datatypes ((tuple%0. 0)) (((tuple%0./tuple%0))))
(declare-fun Poly%tuple%0. (tuple%0.) Poly)
(declare-fun %Poly%tuple%0. (Poly) tuple%0.)
(assert
 (forall ((x tuple%0.)) (!
   (= x (%Poly%tuple%0. (Poly%tuple%0. x)))
   :pattern ((Poly%tuple%0. x))
   :qid internal_crate__tuple__0_box_axiom_definition
   :skolemid skolem_internal_crate__tuple__0_box_axiom_definition
)))
(assert
 (forall ((x Poly)) (!
   (=>
    (has_type x TYPE%tuple%0.)
    (= x (Poly%tuple%0. (%Poly%tuple%0. x)))
   )
   :pattern ((has_type x TYPE%tuple%0.))
   :qid internal_crate__tuple__0_unbox_axiom_definition
   :skolemid skolem_internal_crate__tuple__0_unbox_axiom_definition
)))
(assert
 (forall ((x tuple%0.)) (!
   (has_type (Poly%tuple%0. x) TYPE%tuple%0.)
   :pattern ((has_type (Poly%tuple%0. x) TYPE%tuple%0.))
   :qid internal_crate__tuple__0_has_type_always_definition
   :skolemid skolem_internal_crate__tuple__0_has_type_always_definition
)))
(assert
 (forall ((Self%&. Dcr) (Self%& Type) (Rhs&. Dcr) (Rhs& Type)) (!
   (=>
    (tr_bound%core!ops.arith.Div. Self%&. Self%& Rhs&. Rhs&)
    (and
     (sized Rhs&.)
     (sized (proj%%core!ops.arith.Div./Output Self%&. Self%& Rhs&. Rhs&))
   ))
   :pattern ((tr_bound%core!ops.arith.Div. Self%&. Self%& Rhs&. Rhs&))
   :qid internal_core__ops__arith__Div_trait_type_bounds_definition
   :skolemid skolem_internal_core__ops__arith__Div_trait_type_bounds_definition
)))
(assert
 (forall ((Self%&. Dcr) (Self%& Type) (Rhs&. Dcr) (Rhs& Type)) (!
   (=>
    (tr_bound%vstd!std_specs.ops.DivSpec. Self%&. Self%& Rhs&. Rhs&)
    (and
     (tr_bound%core!ops.arith.Div. Self%&. Self%& Rhs&. Rhs&)
     (sized Rhs&.)
   ))
   :pattern ((tr_bound%vstd!std_specs.ops.DivSpec. Self%&. Self%& Rhs&. Rhs&))
   :qid internal_vstd__std_specs__ops__DivSpec_trait_type_bounds_definition
   :skolemid skolem_internal_vstd__std_specs__ops__DivSpec_trait_type_bounds_definition
)))
(assert
 (= (proj%%core!ops.arith.Div./Output (REF $) (SINT 64) $ (SINT 64)) $)
)
(assert
 (= (proj%core!ops.arith.Div./Output (REF $) (SINT 64) $ (SINT 64)) (SINT 64))
)
(assert
 (= (proj%%core!ops.arith.Div./Output (REF $) (SINT 64) (REF $) (SINT 64)) $)
)
(assert
 (= (proj%core!ops.arith.Div./Output (REF $) (SINT 64) (REF $) (SINT 64)) (SINT 64))
)
(assert
 (= (proj%%core!ops.arith.Div./Output $ (SINT 64) $ (SINT 64)) $)
)
(assert
 (= (proj%core!ops.arith.Div./Output $ (SINT 64) $ (SINT 64)) (SINT 64))
)
(assert
 (= (proj%%core!ops.arith.Div./Output $ (SINT 64) (REF $) (SINT 64)) $)
)
(assert
 (= (proj%core!ops.arith.Div./Output $ (SINT 64) (REF $) (SINT 64)) (SINT 64))
)
(declare-fun vstd!std_specs.ops.DivSpec.div_req.? (Dcr Type Dcr Type Poly Poly) Poly)
(declare-fun vstd!std_specs.ops.DivSpec.div_req%default%.? (Dcr Type Dcr Type Poly
  Poly
 ) Poly
)
(declare-fun vstd!std_specs.ops.DivSpec.obeys_div_spec.? (Dcr Type Dcr Type) Poly)
(declare-fun vstd!std_specs.ops.DivSpec.obeys_div_spec%default%.? (Dcr Type Dcr Type)
 Poly
)
(declare-fun vstd!std_specs.ops.DivSpec.div_spec.? (Dcr Type Dcr Type Poly Poly) Poly)
(declare-fun vstd!std_specs.ops.DivSpec.div_spec%default%.? (Dcr Type Dcr Type Poly
  Poly
 ) Poly
)
(declare-fun candidate!min_val.? (Poly Poly) Int)
(declare-fun candidate!candies_after_division.? (Poly Poly Poly Poly) Int)
(declare-fun candidate!is_achievable.? (Poly Poly Poly Poly) Bool)
(declare-fun candidate!is_optimal.? (Poly Poly Poly Poly) Bool)
(assert
 (forall ((Self%&. Dcr) (Self%& Type) (Rhs&. Dcr) (Rhs& Type) (self! Poly) (rhs! Poly))
  (!
   (=>
    (and
     (has_type self! Self%&)
     (has_type rhs! Rhs&)
    )
    (has_type (vstd!std_specs.ops.DivSpec.div_req.? Self%&. Self%& Rhs&. Rhs& self! rhs!)
     BOOL
   ))
   :pattern ((vstd!std_specs.ops.DivSpec.div_req.? Self%&. Self%& Rhs&. Rhs& self! rhs!))
   :qid internal_vstd!std_specs.ops.DivSpec.div_req.?_pre_post_definition
   :skolemid skolem_internal_vstd!std_specs.ops.DivSpec.div_req.?_pre_post_definition
)))
(assert
 (forall ((Self%&. Dcr) (Self%& Type) (Rhs&. Dcr) (Rhs& Type)) (!
   (has_type (vstd!std_specs.ops.DivSpec.obeys_div_spec.? Self%&. Self%& Rhs&. Rhs&)
    BOOL
   )
   :pattern ((vstd!std_specs.ops.DivSpec.obeys_div_spec.? Self%&. Self%& Rhs&. Rhs&))
   :qid internal_vstd!std_specs.ops.DivSpec.obeys_div_spec.?_pre_post_definition
   :skolemid skolem_internal_vstd!std_specs.ops.DivSpec.obeys_div_spec.?_pre_post_definition
)))
(assert
 (forall ((Self%&. Dcr) (Self%& Type) (Rhs&. Dcr) (Rhs& Type) (self! Poly) (rhs! Poly))
  (!
   (=>
    (and
     (has_type self! Self%&)
     (has_type rhs! Rhs&)
    )
    (has_type (vstd!std_specs.ops.DivSpec.div_spec.? Self%&. Self%& Rhs&. Rhs& self! rhs!)
     (proj%core!ops.arith.Div./Output Self%&. Self%& Rhs&. Rhs&)
   ))
   :pattern ((vstd!std_specs.ops.DivSpec.div_spec.? Self%&. Self%& Rhs&. Rhs& self! rhs!))
   :qid internal_vstd!std_specs.ops.DivSpec.div_spec.?_pre_post_definition
   :skolemid skolem_internal_vstd!std_specs.ops.DivSpec.div_spec.?_pre_post_definition
)))
(declare-fun req%core!ops.arith.Div.div. (Dcr Type Dcr Type Poly Poly) Bool)
(declare-const %%global_location_label%%0 Bool)
(assert
 (forall ((Self%&. Dcr) (Self%& Type) (Rhs&. Dcr) (Rhs& Type) (self! Poly) (rhs! Poly))
  (!
   (= (req%core!ops.arith.Div.div. Self%&. Self%& Rhs&. Rhs& self! rhs!) (=>
     %%global_location_label%%0
     (%B (vstd!std_specs.ops.DivSpec.div_req.? Self%&. Self%& Rhs&. Rhs& self! rhs!))
   ))
   :pattern ((req%core!ops.arith.Div.div. Self%&. Self%& Rhs&. Rhs& self! rhs!))
   :qid internal_req__core!ops.arith.Div.div._definition
   :skolemid skolem_internal_req__core!ops.arith.Div.div._definition
)))
(declare-fun ens%core!ops.arith.Div.div. (Dcr Type Dcr Type Poly Poly Poly) Bool)
(assert
 (forall ((Self%&. Dcr) (Self%& Type) (Rhs&. Dcr) (Rhs& Type) (self! Poly) (rhs! Poly)
   (ret! Poly)
  ) (!
   (= (ens%core!ops.arith.Div.div. Self%&. Self%& Rhs&. Rhs& self! rhs! ret!) (and
     (has_type ret! (proj%core!ops.arith.Div./Output Self%&. Self%& Rhs&. Rhs&))
     (=>
      (%B (vstd!std_specs.ops.DivSpec.obeys_div_spec.? Self%&. Self%& Rhs&. Rhs&))
      (= ret! (vstd!std_specs.ops.DivSpec.div_spec.? Self%&. Self%& Rhs&. Rhs& self! rhs!))
   )))
   :pattern ((ens%core!ops.arith.Div.div. Self%&. Self%& Rhs&. Rhs& self! rhs! ret!))
   :qid internal_ens__core!ops.arith.Div.div._definition
   :skolemid skolem_internal_ens__core!ops.arith.Div.div._definition
)))
(assert
 (fuel_bool_default fuel%vstd!std_specs.ops.impl&%77.obeys_div_spec.)
)
(assert
 (=>
  (fuel_bool fuel%vstd!std_specs.ops.impl&%77.obeys_div_spec.)
  (= (vstd!std_specs.ops.DivSpec.obeys_div_spec.? $ (SINT 64) $ (SINT 64)) (B true))
))
(assert
 (fuel_bool_default fuel%vstd!std_specs.ops.impl&%77.div_req.)
)
(assert
 (=>
  (fuel_bool fuel%vstd!std_specs.ops.impl&%77.div_req.)
  (forall ((self! Poly) (rhs! Poly)) (!
    (= (vstd!std_specs.ops.DivSpec.div_req.? $ (SINT 64) $ (SINT 64) self! rhs!) (B (and
       (not (= (%I rhs!) 0))
       (not (and
         (= (%I self!) (- 9223372036854775808))
         (= (%I rhs!) (Sub 0 1))
    )))))
    :pattern ((vstd!std_specs.ops.DivSpec.div_req.? $ (SINT 64) $ (SINT 64) self! rhs!))
    :qid internal_vstd!std_specs.ops.DivSpec.div_req.?_definition
    :skolemid skolem_internal_vstd!std_specs.ops.DivSpec.div_req.?_definition
))))
(assert
 (fuel_bool_default fuel%vstd!std_specs.ops.impl&%77.div_spec.)
)
(assert
 (=>
  (fuel_bool fuel%vstd!std_specs.ops.impl&%77.div_spec.)
  (forall ((self! Poly) (rhs! Poly)) (!
    (= (vstd!std_specs.ops.DivSpec.div_spec.? $ (SINT 64) $ (SINT 64) self! rhs!) (I (ite
       (>= (%I self!) 0)
       (iClip 64 (EucDiv (%I self!) (%I rhs!)))
       (iClip 64 (Sub 0 (EucDiv (Sub 0 (%I self!)) (%I rhs!))))
    )))
    :pattern ((vstd!std_specs.ops.DivSpec.div_spec.? $ (SINT 64) $ (SINT 64) self! rhs!))
    :qid internal_vstd!std_specs.ops.DivSpec.div_spec.?_definition
    :skolemid skolem_internal_vstd!std_specs.ops.DivSpec.div_spec.?_definition
))))
(assert
 (fuel_bool_default fuel%candidate!min_val.)
)
(assert
 (=>
  (fuel_bool fuel%candidate!min_val.)
  (forall ((x! Poly) (y! Poly)) (!
    (= (candidate!min_val.? x! y!) (%I (ite
       (<= (%I x!) (%I y!))
       x!
       y!
    )))
    :pattern ((candidate!min_val.? x! y!))
    :qid internal_candidate!min_val.?_definition
    :skolemid skolem_internal_candidate!min_val.?_definition
))))
(assert
 (fuel_bool_default fuel%candidate!candies_after_division.)
)
(assert
 (=>
  (fuel_bool fuel%candidate!candies_after_division.)
  (forall ((ap! Poly) (bp! Poly) (sp! Poly) (s! Poly)) (!
    (= (candidate!candies_after_division.? ap! bp! sp! s!) (candidate!min_val.? (I (Add (
         %I ap!
        ) (%I s!)
       )
      ) (I (Add (%I bp!) (Sub (%I sp!) (%I s!))))
    ))
    :pattern ((candidate!candies_after_division.? ap! bp! sp! s!))
    :qid internal_candidate!candies_after_division.?_definition
    :skolemid skolem_internal_candidate!candies_after_division.?_definition
))))
(assert
 (fuel_bool_default fuel%candidate!is_achievable.)
)
(assert
 (=>
  (fuel_bool fuel%candidate!is_achievable.)
  (forall ((a! Poly) (b! Poly) (c! Poly) (result! Poly)) (!
    (= (candidate!is_achievable.? a! b! c! result!) (or
      (or
       (exists ((s$ Poly)) (!
         (and
          (has_type s$ INT)
          (and
           (let
            ((tmp%%$ 0))
            (let
             ((tmp%%$1 (%I s$)))
             (let
              ((tmp%%$2 (%I c!)))
              (and
               (<= tmp%%$ tmp%%$1)
               (<= tmp%%$1 tmp%%$2)
           ))))
           (= (candidate!candies_after_division.? a! b! c! s$) (%I result!))
         ))
         :pattern ((candidate!candies_after_division.? a! b! c! s$))
         :qid user_candidate__is_achievable_0
         :skolemid skolem_user_candidate__is_achievable_0
       ))
       (exists ((s$ Poly)) (!
         (and
          (has_type s$ INT)
          (and
           (let
            ((tmp%%$ 0))
            (let
             ((tmp%%$4 (%I s$)))
             (let
              ((tmp%%$5 (%I b!)))
              (and
               (<= tmp%%$ tmp%%$4)
               (<= tmp%%$4 tmp%%$5)
           ))))
           (= (candidate!candies_after_division.? a! c! b! s$) (%I result!))
         ))
         :pattern ((candidate!candies_after_division.? a! c! b! s$))
         :qid user_candidate__is_achievable_1
         :skolemid skolem_user_candidate__is_achievable_1
      )))
      (exists ((s$ Poly)) (!
        (and
         (has_type s$ INT)
         (and
          (let
           ((tmp%%$ 0))
           (let
            ((tmp%%$7 (%I s$)))
            (let
             ((tmp%%$8 (%I a!)))
             (and
              (<= tmp%%$ tmp%%$7)
              (<= tmp%%$7 tmp%%$8)
          ))))
          (= (candidate!candies_after_division.? b! c! a! s$) (%I result!))
        ))
        :pattern ((candidate!candies_after_division.? b! c! a! s$))
        :qid user_candidate__is_achievable_2
        :skolemid skolem_user_candidate__is_achievable_2
    ))))
    :pattern ((candidate!is_achievable.? a! b! c! result!))
    :qid internal_candidate!is_achievable.?_definition
    :skolemid skolem_internal_candidate!is_achievable.?_definition
))))
(assert
 (fuel_bool_default fuel%candidate!is_optimal.)
)
(assert
 (=>
  (fuel_bool fuel%candidate!is_optimal.)
  (forall ((a! Poly) (b! Poly) (c! Poly) (result! Poly)) (!
    (= (candidate!is_optimal.? a! b! c! result!) (and
      (and
       (forall ((s$ Poly)) (!
         (=>
          (has_type s$ INT)
          (=>
           (let
            ((tmp%%$ 0))
            (let
             ((tmp%%$1 (%I s$)))
             (let
              ((tmp%%$2 (%I c!)))
              (and
               (<= tmp%%$ tmp%%$1)
               (<= tmp%%$1 tmp%%$2)
           ))))
           (<= (candidate!candies_after_division.? a! b! c! s$) (%I result!))
         ))
         :pattern ((candidate!candies_after_division.? a! b! c! s$))
         :qid user_candidate__is_optimal_3
         :skolemid skolem_user_candidate__is_optimal_3
       ))
       (forall ((s$ Poly)) (!
         (=>
          (has_type s$ INT)
          (=>
           (let
            ((tmp%%$ 0))
            (let
             ((tmp%%$4 (%I s$)))
             (let
              ((tmp%%$5 (%I b!)))
              (and
               (<= tmp%%$ tmp%%$4)
               (<= tmp%%$4 tmp%%$5)
           ))))
           (<= (candidate!candies_after_division.? a! c! b! s$) (%I result!))
         ))
         :pattern ((candidate!candies_after_division.? a! c! b! s$))
         :qid user_candidate__is_optimal_4
         :skolemid skolem_user_candidate__is_optimal_4
      )))
      (forall ((s$ Poly)) (!
        (=>
         (has_type s$ INT)
         (=>
          (let
           ((tmp%%$ 0))
           (let
            ((tmp%%$7 (%I s$)))
            (let
             ((tmp%%$8 (%I a!)))
             (and
              (<= tmp%%$ tmp%%$7)
              (<= tmp%%$7 tmp%%$8)
          ))))
          (<= (candidate!candies_after_division.? b! c! a! s$) (%I result!))
        ))
        :pattern ((candidate!candies_after_division.? b! c! a! s$))
        :qid user_candidate__is_optimal_5
        :skolemid skolem_user_candidate__is_optimal_5
    ))))
    :pattern ((candidate!is_optimal.? a! b! c! result!))
    :qid internal_candidate!is_optimal.?_definition
    :skolemid skolem_internal_candidate!is_optimal.?_definition
))))
(assert
 (tr_bound%core!ops.arith.Div. $ (SINT 64) $ (SINT 64))
)
(assert
 (tr_bound%vstd!std_specs.ops.DivSpec. $ (SINT 64) $ (SINT 64))
)
(assert
 (tr_bound%core!ops.arith.Div. (REF $) (SINT 64) $ (SINT 64))
)
(assert
 (tr_bound%core!ops.arith.Div. (REF $) (SINT 64) (REF $) (SINT 64))
)
(assert
 (tr_bound%core!ops.arith.Div. $ (SINT 64) (REF $) (SINT 64))
)
(assert
 (forall ((Rhs&. Dcr) (Rhs& Type) (VERUS_SPEC__A&. Dcr) (VERUS_SPEC__A& Type)) (!
   (=>
    (and
     (sized Rhs&.)
     (tr_bound%core!ops.arith.Div. VERUS_SPEC__A&. VERUS_SPEC__A& Rhs&. Rhs&)
    )
    (tr_bound%vstd!std_specs.ops.DivSpec. VERUS_SPEC__A&. VERUS_SPEC__A& Rhs&. Rhs&)
   )
   :pattern ((tr_bound%vstd!std_specs.ops.DivSpec. VERUS_SPEC__A&. VERUS_SPEC__A& Rhs&.
     Rhs&
   ))
   :qid internal_vstd__std_specs__ops__impl&__146_trait_impl_definition
   :skolemid skolem_internal_vstd__std_specs__ops__impl&__146_trait_impl_definition
)))
(declare-fun ens%candidate!lemma_min_le_half_sum. (Int Int) Bool)
(assert
 (forall ((x! Int) (y! Int)) (!
   (= (ens%candidate!lemma_min_le_half_sum. x! y!) (<= (candidate!min_val.? (I x!) (I y!))
     (EucDiv (Add x! y!) 2)
   ))
   :pattern ((ens%candidate!lemma_min_le_half_sum. x! y!))
   :qid internal_ens__candidate!lemma_min_le_half_sum._definition
   :skolemid skolem_internal_ens__candidate!lemma_min_le_half_sum._definition
)))
(push)
(declare-const x! Int)
(declare-const y! Int)
(declare-const tmp%1 Bool)
(assert
 fuel_defaults
)
(declare-const %%location_label%%0 Bool)
(declare-const %%location_label%%1 Bool)
(assert
 (not (=>
   (= tmp%1 (<= (Mul 2 (candidate!min_val.? (I x!) (I y!))) (Add x! y!)))
   (and
    (=>
     %%location_label%%0
     tmp%1
    )
    (=>
     tmp%1
     (=>
      %%location_label%%1
      (<= (candidate!min_val.? (I x!) (I y!)) (EucDiv (Add x! y!) 2))
))))))
(set-option :rlimit 30000000)
(set-option :rlimit 0)
(pop)
(declare-fun req%candidate!three_piles_of_candies. (Int Int Int) Bool)
(declare-const %%global_location_label%%1 Bool)
(declare-const %%global_location_label%%2 Bool)
(declare-const %%global_location_label%%3 Bool)
(declare-const %%global_location_label%%4 Bool)
(assert
 (forall ((a! Int) (b! Int) (c! Int)) (!
   (= (req%candidate!three_piles_of_candies. a! b! c!) (and
     (=>
      %%global_location_label%%1
      (>= a! 0)
     )
     (=>
      %%global_location_label%%2
      (>= b! 0)
     )
     (=>
      %%global_location_label%%3
      (>= c! 0)
     )
     (=>
      %%global_location_label%%4
      (<= (Add (Add a! b!) c!) 9223372036854775807)
   )))
   :pattern ((req%candidate!three_piles_of_candies. a! b! c!))
   :qid internal_req__candidate!three_piles_of_candies._definition
   :skolemid skolem_internal_req__candidate!three_piles_of_candies._definition
)))
(declare-fun ens%candidate!three_piles_of_candies. (Int Int Int Int) Bool)
(assert
 (forall ((a! Int) (b! Int) (c! Int) (max_candies! Int)) (!
   (= (ens%candidate!three_piles_of_candies. a! b! c! max_candies!) (and
     (iInv 64 max_candies!)
     (candidate!is_achievable.? (I a!) (I b!) (I c!) (I max_candies!))
     (candidate!is_optimal.? (I a!) (I b!) (I c!) (I max_candies!))
   ))
   :pattern ((ens%candidate!three_piles_of_candies. a! b! c! max_candies!))
   :qid internal_ens__candidate!three_piles_of_candies._definition
   :skolemid skolem_internal_ens__candidate!three_piles_of_candies._definition
)))
(push)
(declare-const max_candies! Int)
(declare-const a! Int)
(declare-const b! Int)
(declare-const c! Int)
(declare-const tmp%1 Poly)
(declare-const tmp%2 Poly)
(declare-const tmp%3 Bool)
(declare-const s@ Poly)
(declare-const tmp%4 Int)
(declare-const tmp%5 Int)
(declare-const s$1@ Poly)
(declare-const tmp%6 Int)
(declare-const tmp%7 Int)
(declare-const s$2@ Poly)
(declare-const tmp%8 Int)
(declare-const tmp%9 Int)
(declare-const tmp%10 Bool)
(declare-const tmp%11 Bool)
(declare-const tmp%12 Bool)
(declare-const tmp%13 Bool)
(declare-const s$3@ Int)
(declare-const tmp%14 Bool)
(declare-const tmp%15 Bool)
(declare-const tmp%16 Bool)
(declare-const tmp%17 Bool)
(declare-const s$4@ Int)
(declare-const tmp%18 Bool)
(declare-const tmp%19 Bool)
(declare-const tmp%20 Bool)
(declare-const tmp%21 Bool)
(declare-const s$5@ Int)
(declare-const a_@ Int)
(declare-const b_@ Int)
(declare-const c_@ Int)
(declare-const r@ Int)
(declare-const max_candies@ Int)
(assert
 fuel_defaults
)
(assert
 (iInv 64 a!)
)
(assert
 (iInv 64 b!)
)
(assert
 (iInv 64 c!)
)
(assert
 (>= a! 0)
)
(assert
 (>= b! 0)
)
(assert
 (>= c! 0)
)
(assert
 (<= (Add (Add a! b!) c!) 9223372036854775807)
)
(declare-const %%switch_label%%0 Bool)
(declare-const %%switch_label%%1 Bool)
(declare-const %%location_label%%0 Bool)
(declare-const %%location_label%%1 Bool)
(declare-const %%location_label%%2 Bool)
(declare-const %%location_label%%3 Bool)
(declare-const %%location_label%%4 Bool)
(declare-const %%location_label%%5 Bool)
(declare-const %%location_label%%6 Bool)
(declare-const %%location_label%%7 Bool)
(declare-const %%location_label%%8 Bool)
(declare-const %%location_label%%9 Bool)
(declare-const %%location_label%%10 Bool)
(declare-const %%location_label%%11 Bool)
(declare-const %%location_label%%12 Bool)
(declare-const %%location_label%%13 Bool)
(declare-const %%location_label%%14 Bool)
(declare-const %%location_label%%15 Bool)
(declare-const %%location_label%%16 Bool)
(declare-const %%location_label%%17 Bool)
(declare-const %%location_label%%18 Bool)
(declare-const %%location_label%%19 Bool)
(declare-const %%location_label%%20 Bool)
(declare-const %%location_label%%21 Bool)
(declare-const %%location_label%%22 Bool)
(declare-const %%location_label%%23 Bool)
(assert
 (not (and
   (=>
    %%location_label%%0
    (iInv 64 (Add a! b!))
   )
   (=>
    (iInv 64 (Add a! b!))
    (and
     (=>
      %%location_label%%1
      (iInv 64 (Add (iClip 64 (Add a! b!)) c!))
     )
     (=>
      (iInv 64 (Add (iClip 64 (Add a! b!)) c!))
      (=>
       (= tmp%2 (I (iClip 64 (Add (iClip 64 (Add a! b!)) c!))))
       (and
        (=>
         %%location_label%%2
         (req%core!ops.arith.Div.div. $ (SINT 64) $ (SINT 64) tmp%2 (I 2))
        )
        (=>
         (ens%core!ops.arith.Div.div. $ (SINT 64) $ (SINT 64) tmp%2 (I 2) tmp%1)
         (=>
          (= max_candies@ (%I tmp%1))
          (=>
           (= a_@ a!)
           (=>
            (= b_@ b!)
            (=>
             (= c_@ c!)
             (=>
              (= r@ max_candies@)
              (=>
               (= tmp%3 (= r@ (EucDiv (Add (Add a_@ b_@) c_@) 2)))
               (and
                (=>
                 %%location_label%%3
                 tmp%3
                )
                (=>
                 tmp%3
                 (and
                  (=>
                   (has_type s@ INT)
                   (=>
                    (let
                     ((tmp%%$ 0))
                     (let
                      ((tmp%%$1 (%I s@)))
                      (let
                       ((tmp%%$2 c_@))
                       (and
                        (<= tmp%%$ tmp%%$1)
                        (<= tmp%%$1 tmp%%$2)
                    ))))
                    (=>
                     (= tmp%4 (Add a_@ (%I s@)))
                     (=>
                      (= tmp%5 (Add b_@ (Sub c_@ (%I s@))))
                      (=>
                       (ens%candidate!lemma_min_le_half_sum. tmp%4 tmp%5)
                       (=>
                        %%location_label%%4
                        (<= (candidate!candies_after_division.? (I a_@) (I b_@) (I c_@) s@) r@)
                  ))))))
                  (=>
                   (forall ((s$ Poly)) (!
                     (=>
                      (has_type s$ INT)
                      (=>
                       (let
                        ((tmp%%$ 0))
                        (let
                         ((tmp%%$4 (%I s$)))
                         (let
                          ((tmp%%$5 c_@))
                          (and
                           (<= tmp%%$ tmp%%$4)
                           (<= tmp%%$4 tmp%%$5)
                       ))))
                       (<= (candidate!candies_after_division.? (I a_@) (I b_@) (I c_@) s$) r@)
                     ))
                     :pattern ((candidate!candies_after_division.? (I a_@) (I b_@) (I c_@) s$))
                     :qid user_candidate__three_piles_of_candies_6
                     :skolemid skolem_user_candidate__three_piles_of_candies_6
                   ))
                   (and
                    (=>
                     (has_type s$1@ INT)
                     (=>
                      (let
                       ((tmp%%$ 0))
                       (let
                        ((tmp%%$7 (%I s$1@)))
                        (let
                         ((tmp%%$8 b_@))
                         (and
                          (<= tmp%%$ tmp%%$7)
                          (<= tmp%%$7 tmp%%$8)
                      ))))
                      (=>
                       (= tmp%6 (Add a_@ (%I s$1@)))
                       (=>
                        (= tmp%7 (Add c_@ (Sub b_@ (%I s$1@))))
                        (=>
                         (ens%candidate!lemma_min_le_half_sum. tmp%6 tmp%7)
                         (=>
                          %%location_label%%5
                          (<= (candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) s$1@) r@)
                    ))))))
                    (=>
                     (forall ((s$ Poly)) (!
                       (=>
                        (has_type s$ INT)
                        (=>
                         (let
                          ((tmp%%$ 0))
                          (let
                           ((tmp%%$10 (%I s$)))
                           (let
                            ((tmp%%$11 b_@))
                            (and
                             (<= tmp%%$ tmp%%$10)
                             (<= tmp%%$10 tmp%%$11)
                         ))))
                         (<= (candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) s$) r@)
                       ))
                       :pattern ((candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) s$))
                       :qid user_candidate__three_piles_of_candies_7
                       :skolemid skolem_user_candidate__three_piles_of_candies_7
                     ))
                     (and
                      (=>
                       (has_type s$2@ INT)
                       (=>
                        (let
                         ((tmp%%$ 0))
                         (let
                          ((tmp%%$13 (%I s$2@)))
                          (let
                           ((tmp%%$14 a_@))
                           (and
                            (<= tmp%%$ tmp%%$13)
                            (<= tmp%%$13 tmp%%$14)
                        ))))
                        (=>
                         (= tmp%8 (Add b_@ (%I s$2@)))
                         (=>
                          (= tmp%9 (Add c_@ (Sub a_@ (%I s$2@))))
                          (=>
                           (ens%candidate!lemma_min_le_half_sum. tmp%8 tmp%9)
                           (=>
                            %%location_label%%6
                            (<= (candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) s$2@) r@)
                      ))))))
                      (=>
                       (forall ((s$ Poly)) (!
                         (=>
                          (has_type s$ INT)
                          (=>
                           (let
                            ((tmp%%$ 0))
                            (let
                             ((tmp%%$16 (%I s$)))
                             (let
                              ((tmp%%$17 a_@))
                              (and
                               (<= tmp%%$ tmp%%$16)
                               (<= tmp%%$16 tmp%%$17)
                           ))))
                           (<= (candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) s$) r@)
                         ))
                         :pattern ((candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) s$))
                         :qid user_candidate__three_piles_of_candies_8
                         :skolemid skolem_user_candidate__three_piles_of_candies_8
                       ))
                       (or
                        (and
                         (=>
                          (and
                           (>= a_@ b_@)
                           (>= a_@ c_@)
                          )
                          (and
                           (=>
                            (= s$3@ (Sub r@ b_@))
                            (=>
                             (= tmp%10 (and
                               (<= 0 s$3@)
                               (<= s$3@ a_@)
                             ))
                             (and
                              (=>
                               %%location_label%%7
                               tmp%10
                              )
                              (=>
                               tmp%10
                               (=>
                                (= tmp%11 (= (Add b_@ s$3@) r@))
                                (and
                                 (=>
                                  %%location_label%%8
                                  tmp%11
                                 )
                                 (=>
                                  tmp%11
                                  (=>
                                   (= tmp%12 (>= (Add c_@ (Sub a_@ s$3@)) r@))
                                   (and
                                    (=>
                                     %%location_label%%9
                                     tmp%12
                                    )
                                    (=>
                                     tmp%12
                                     (=>
                                      (= tmp%13 (= (candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) (I s$3@))
                                        r@
                                      ))
                                      (and
                                       (=>
                                        %%location_label%%10
                                        tmp%13
                                       )
                                       (=>
                                        tmp%13
                                        (=>
                                         %%location_label%%11
                                         (exists ((s$ Poly)) (!
                                           (and
                                            (has_type s$ INT)
                                            (and
                                             (let
                                              ((tmp%%$ 0))
                                              (let
                                               ((tmp%%$19 (%I s$)))
                                               (let
                                                ((tmp%%$20 a_@))
                                                (and
                                                 (<= tmp%%$ tmp%%$19)
                                                 (<= tmp%%$19 tmp%%$20)
                                             ))))
                                             (= (candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) s$) r@)
                                           ))
                                           :pattern ((candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) s$))
                                           :qid user_candidate__three_piles_of_candies_9
                                           :skolemid skolem_user_candidate__three_piles_of_candies_9
                           ))))))))))))))))
                           (=>
                            (exists ((s$ Poly)) (!
                              (and
                               (has_type s$ INT)
                               (and
                                (let
                                 ((tmp%%$ 0))
                                 (let
                                  ((tmp%%$22 (%I s$)))
                                  (let
                                   ((tmp%%$23 a_@))
                                   (and
                                    (<= tmp%%$ tmp%%$22)
                                    (<= tmp%%$22 tmp%%$23)
                                ))))
                                (= (candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) s$) r@)
                              ))
                              :pattern ((candidate!candies_after_division.? (I b_@) (I c_@) (I a_@) s$))
                              :qid user_candidate__three_piles_of_candies_10
                              :skolemid skolem_user_candidate__three_piles_of_candies_10
                            ))
                            %%switch_label%%0
                         )))
                         (=>
                          (not (and
                            (>= a_@ b_@)
                            (>= a_@ c_@)
                          ))
                          (or
                           (and
                            (=>
                             (and
                              (>= b_@ a_@)
                              (>= b_@ c_@)
                             )
                             (and
                              (=>
                               (= s$4@ (Sub r@ a_@))
                               (=>
                                (= tmp%14 (and
                                  (<= 0 s$4@)
                                  (<= s$4@ b_@)
                                ))
                                (and
                                 (=>
                                  %%location_label%%12
                                  tmp%14
                                 )
                                 (=>
                                  tmp%14
                                  (=>
                                   (= tmp%15 (= (Add a_@ s$4@) r@))
                                   (and
                                    (=>
                                     %%location_label%%13
                                     tmp%15
                                    )
                                    (=>
                                     tmp%15
                                     (=>
                                      (= tmp%16 (>= (Add c_@ (Sub b_@ s$4@)) r@))
                                      (and
                                       (=>
                                        %%location_label%%14
                                        tmp%16
                                       )
                                       (=>
                                        tmp%16
                                        (=>
                                         (= tmp%17 (= (candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) (I s$4@))
                                           r@
                                         ))
                                         (and
                                          (=>
                                           %%location_label%%15
                                           tmp%17
                                          )
                                          (=>
                                           tmp%17
                                           (=>
                                            %%location_label%%16
                                            (exists ((s$ Poly)) (!
                                              (and
                                               (has_type s$ INT)
                                               (and
                                                (let
                                                 ((tmp%%$ 0))
                                                 (let
                                                  ((tmp%%$25 (%I s$)))
                                                  (let
                                                   ((tmp%%$26 b_@))
                                                   (and
                                                    (<= tmp%%$ tmp%%$25)
                                                    (<= tmp%%$25 tmp%%$26)
                                                ))))
                                                (= (candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) s$) r@)
                                              ))
                                              :pattern ((candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) s$))
                                              :qid user_candidate__three_piles_of_candies_12
                                              :skolemid skolem_user_candidate__three_piles_of_candies_12
                              ))))))))))))))))
                              (=>
                               (exists ((s$ Poly)) (!
                                 (and
                                  (has_type s$ INT)
                                  (and
                                   (let
                                    ((tmp%%$ 0))
                                    (let
                                     ((tmp%%$28 (%I s$)))
                                     (let
                                      ((tmp%%$29 b_@))
                                      (and
                                       (<= tmp%%$ tmp%%$28)
                                       (<= tmp%%$28 tmp%%$29)
                                   ))))
                                   (= (candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) s$) r@)
                                 ))
                                 :pattern ((candidate!candies_after_division.? (I a_@) (I c_@) (I b_@) s$))
                                 :qid user_candidate__three_piles_of_candies_13
                                 :skolemid skolem_user_candidate__three_piles_of_candies_13
                               ))
                               %%switch_label%%1
                            )))
                            (=>
                             (not (and
                               (>= b_@ a_@)
                               (>= b_@ c_@)
                             ))
                             (and
                              (=>
                               (= s$5@ (Sub r@ a_@))
                               (=>
                                (= tmp%18 (and
                                  (>= c_@ a_@)
                                  (>= c_@ b_@)
                                ))
                                (and
                                 (=>
                                  %%location_label%%17
                                  tmp%18
                                 )
                                 (=>
                                  tmp%18
                                  (=>
                                   (= tmp%19 (and
                                     (<= 0 s$5@)
                                     (<= s$5@ c_@)
                                   ))
                                   (and
                                    (=>
                                     %%location_label%%18
                                     tmp%19
                                    )
                                    (=>
                                     tmp%19
                                     (=>
                                      (= tmp%20 (= (Add a_@ s$5@) r@))
                                      (and
                                       (=>
                                        %%location_label%%19
                                        tmp%20
                                       )
                                       (=>
                                        tmp%20
                                        (=>
                                         (= tmp%21 (>= (Add b_@ (Sub c_@ s$5@)) r@))
                                         (and
                                          (=>
                                           %%location_label%%20
                                           tmp%21
                                          )
                                          (=>
                                           tmp%21
                                           (=>
                                            %%location_label%%21
                                            (exists ((s$ Poly)) (!
                                              (and
                                               (has_type s$ INT)
                                               (and
                                                (let
                                                 ((tmp%%$ 0))
                                                 (let
                                                  ((tmp%%$31 (%I s$)))
                                                  (let
                                                   ((tmp%%$32 c_@))
                                                   (and
                                                    (<= tmp%%$ tmp%%$31)
                                                    (<= tmp%%$31 tmp%%$32)
                                                ))))
                                                (= (candidate!candies_after_division.? (I a_@) (I b_@) (I c_@) s$) r@)
                                              ))
                                              :pattern ((candidate!candies_after_division.? (I a_@) (I b_@) (I c_@) s$))
                                              :qid user_candidate__three_piles_of_candies_15
                                              :skolemid skolem_user_candidate__three_piles_of_candies_15
                              ))))))))))))))))
                              (=>
                               (exists ((s$ Poly)) (!
                                 (and
                                  (has_type s$ INT)
                                  (and
                                   (let
                                    ((tmp%%$ 0))
                                    (let
                                     ((tmp%%$34 (%I s$)))
                                     (let
                                      ((tmp%%$35 c_@))
                                      (and
                                       (<= tmp%%$ tmp%%$34)
                                       (<= tmp%%$34 tmp%%$35)
                                   ))))
                                   (= (candidate!candies_after_division.? (I a_@) (I b_@) (I c_@) s$) r@)
                                 ))
                                 :pattern ((candidate!candies_after_division.? (I a_@) (I b_@) (I c_@) s$))
                                 :qid user_candidate__three_piles_of_candies_16
                                 :skolemid skolem_user_candidate__three_piles_of_candies_16
                               ))
                               %%switch_label%%1
                           ))))
                           (and
                            (not %%switch_label%%1)
                            %%switch_label%%0
                        ))))
                        (and
                         (not %%switch_label%%0)
                         (=>
                          (= max_candies! max_candies@)
                          (and
                           (=>
                            %%location_label%%22
                            (candidate!is_achievable.? (I a!) (I b!) (I c!) (I max_candies!))
                           )
                           (=>
                            %%location_label%%23
                            (candidate!is_optimal.? (I a!) (I b!) (I c!) (I max_candies!))
))))))))))))))))))))))))))))
(set-option :rlimit 30000000)
(check-sat)
