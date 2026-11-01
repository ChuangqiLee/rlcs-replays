"""P6.4 --lowmem entry point with a bit-exact CR1 block.

Job 41114791 showed every lowmem P6 artifact bit-identical to the reference
(tables, moments-driven bootstrap draws, point estimates) except CR1 standard
errors, max rel. error 7.7e-5.  Cause: the lowmem CR1 contracts a strided
*view* moments[:, :k, :k]; einsum on a non-contiguous operand uses a different
summation order than on the C-contiguous copy the reference builds with
moments[:, cols][:, :, cols].  Not float32: all CR1 inputs are float64.

Fix: lowmem keeps its other savings but uses the reference CR1 expression,
whose transient two G*k*k copies are small next to the 192G budget.  Everything else is the unchanged boost_mediation code.
"""
import numpy as np

from tactics_code import boost_mediation as bm


_REFERENCE_CR1 = bm._cr1


def _cr1_exact(moments, q, n, point, *, lowmem=False):
    """Always the reference CR1 code path (incl. its advanced-index copies).

    A contiguous prefix copy is NOT enough: moments[:, cols][:, :, cols]
    yields a non-C-ordered result whose einsum summation order differs, so
    only the literal reference expression is bit-exact.  Cost: two transient
    G*k*k (approx G*(q+3)^2*8 B) float64 blocks, as in the original code.
    """
    return _REFERENCE_CR1(moments, q, n, point, lowmem=False)


def install():
    bm._cr1 = _cr1_exact


if __name__ == '__main__':
    install()
    bm.main()
