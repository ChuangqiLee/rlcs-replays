import unittest
import numpy as np
from tactics_code import boost_mediation as bm
from tactics_code import boost_mediation_lowmem_exact as ex


class CR1Exact(unittest.TestCase):
    def test_bitwise_equal_to_reference(self):
        rng = np.random.default_rng(0)
        for g, q in ((37, 11), (120, 40), (9, 3)):
            z = rng.normal(size=(g, 50, q+3))
            moments = np.einsum('gri,grj->gij', z, z)/50
            point = bm._coefficients(moments.sum(axis=0), q)
            ref = bm._cr1(moments, q, g*50, point, lowmem=False)
            new = ex._cr1_exact(moments, q, g*50, point, lowmem=True)
            self.assertTrue(np.array_equal(ref, new, equal_nan=True), (ref, new))

    def test_install_patches_module(self):
        old = bm._cr1
        try:
            ex.install(); self.assertIs(bm._cr1, ex._cr1_exact)
        finally:
            bm._cr1 = old



class FitExact(unittest.TestCase):
    def test_fit_decomposition_lowmem_bitwise(self):
        rng = np.random.default_rng(3)
        n, p = 3000, 25
        x = rng.normal(size=(n, p)); x[:, 5] = x[:, 4]  # redundant column for QR
        series = rng.integers(0, 40, size=n).astype(str)
        a = rng.integers(0, 2, size=n).astype(float)
        m = x[:, 0] + a + rng.normal(size=n)
        y = (rng.random(n) < 0.3).astype(float)
        old = bm._cr1
        try:
            ref = bm.fit_decomposition(a, m, y, x, series, repeats=50, lowmem=False)
            ex.install()
            new = bm.fit_decomposition(a, m, y, x, series, repeats=50, lowmem=True)
        finally:
            bm._cr1 = old
        def flat(o, out):
            if isinstance(o, dict):
                for k in sorted(o):
                    if 'second' not in k and 'timing' not in k: flat(o[k], out)
            elif isinstance(o, (list, tuple)):
                for v in o: flat(v, out)
            elif isinstance(o, np.ndarray): out.append(o.tolist())
            else: out.append(o)
            return out
        fr, fn = flat(ref, []), flat(new, [])
        self.assertEqual(len(fr), len(fn))
        for u, v in zip(fr, fn):
            if isinstance(u, float) and np.isnan(u): self.assertTrue(np.isnan(v))
            else: self.assertEqual(u, v)


if __name__ == '__main__':
    unittest.main()
