"""Full (non-stopping) P6 reference vs lowmem candidate comparison.

Reports max abs/rel error over every float in boost_mediation.json and
bootstrap_draws.npy, exact checks of tables / non-float JSON values, and
whether conclusion-bearing quantities agree (sign of estimates, CI zero
crossing, every bool/str gate).  Read-only on inputs; prints JSON.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from tactics_code.pushup_dr import guard_path

IGN = {'updated', 'parameters', 'source_provenance', 'source_sha256',
       'timing_seconds', 'timing_seconds_pipeline'}
CI_KEYS = {'ci95', 'bootstrap_ci95', 'cr1_ci95'}
EST_KEYS = {'estimate'}

def rel(a, b):
    d = abs(b - a)
    return 0.0 if d == 0 else (float('inf') if a == 0 else d / abs(a))

class R:
    def __init__(s):
        s.n = 0; s.maxabs = 0.; s.maxrel = 0.; s.worst = []
        s.discrete = []; s.structure = []; s.sign = []; s.ci0 = []; s.nci = 0; s.nest = 0
    def num(s, p, a, b):
        if not (np.isfinite(a) and np.isfinite(b)):
            if not (a == b or (np.isnan(a) and np.isnan(b))):
                s.discrete.append(f'{p}: nonfinite {a!r}->{b!r}')
            return
        s.n += 1; d = abs(b - a); r = rel(a, b)
        s.maxabs = max(s.maxabs, d); s.maxrel = max(s.maxrel, r)
        s.worst.append((r, d, p, a, b))
        if len(s.worst) > 400:
            s.worst = sorted(s.worst, reverse=True)[:20]
    def walk(s, a, b, p='$', key=None):
        if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or a is None:
            if a != b or type(a) is not type(b): s.discrete.append(f'{p}: {a!r}->{b!r}')
            return
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if isinstance(a, int) != isinstance(b, int):
                s.discrete.append(f'{p}: int/float type change {a!r}->{b!r}')
            elif isinstance(a, int) and isinstance(b, int):
                if a != b: s.discrete.append(f'{p}: int {a}->{b}')
            else:
                s.num(p, float(a), float(b))
            return
        if type(a) is not type(b):
            s.structure.append(f'{p}: type {type(a).__name__}->{type(b).__name__}'); return
        if isinstance(a, dict):
            ka, kb = set(a) - IGN, set(b) - IGN
            if ka != kb: s.structure.append(f'{p}: keys {sorted(ka ^ kb)}')
            for k in sorted(ka & kb):
                va, vb = a[k], b[k]
                if k in CI_KEYS and isinstance(va, list) and isinstance(vb, list) and len(va) == 2 == len(vb) \
                        and all(isinstance(x, (int, float)) for x in va + vb):
                    s.nci += 1
                    za = va[0] <= 0 <= va[1]; zb = vb[0] <= 0 <= vb[1]
                    if za != zb or np.sign(va).tolist() != np.sign(vb).tolist():
                        s.ci0.append(f'{p}.{k}: {va}->{vb}')
                if k in EST_KEYS and isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    s.nest += 1
                    if np.sign(va) != np.sign(vb): s.sign.append(f'{p}.{k}: {va}->{vb}')
                s.walk(va, vb, f'{p}.{k}', k)
        elif isinstance(a, list):
            if len(a) != len(b): s.structure.append(f'{p}: len {len(a)}->{len(b)}')
            for i, (x, y) in enumerate(zip(a, b)): s.walk(x, y, f'{p}[{i}]', key)
        else:
            if a != b: s.discrete.append(f'{p}: {a!r}->{b!r}')

def main(ref, cand):
    ref, cand = guard_path(Path(ref)).resolve(), guard_path(Path(cand)).resolve(); r = R(); files = {}
    G = lambda root, name: guard_path(root/name)
    r.walk(json.loads((G(ref, 'boost_mediation.json')).read_text()),
           json.loads((G(cand, 'boost_mediation.json')).read_text()), 'boost_mediation.json')
    json_n, json_abs, json_rel = r.n, r.maxabs, r.maxrel
    sa = json.loads((G(ref, 'selected_replays.json')).read_text()); sb = json.loads((G(cand, 'selected_replays.json')).read_text())
    files['selected_replays.json'] = 'identical' if sa == sb else 'DIFFERENT'
    for t in ('anchors.parquet', 'goal_events.parquet', 'replay_events.parquet'):
        try:
            pd.testing.assert_frame_equal(pd.read_parquet(G(ref, t)), pd.read_parquet(G(cand, t)), check_exact=True)
            files[t] = 'identical (exact)'
        except AssertionError as e:
            files[t] = 'DIFFERENT: ' + str(e)[:300]
    da = np.load(G(ref, 'bootstrap_draws.npy')); db = np.load(G(cand, 'bootstrap_draws.npy'))
    draws = {'shape_ref': list(da.shape), 'shape_cand': list(db.shape), 'dtype_ref': str(da.dtype), 'dtype_cand': str(db.dtype)}
    if da.dtype != db.dtype: r.structure.append('bootstrap_draws.npy dtype differs')
    if da.shape == db.shape:
        ma = [bool(np.array_equal(f(da), f(db))) for f in (np.isnan, np.isposinf, np.isneginf)]
        fin = np.isfinite(da) & np.isfinite(db); d = np.abs(db - da)[fin]; a = np.abs(da[fin])
        rr = np.where(a > 0, d / np.where(a > 0, a, 1), np.where(d > 0, np.inf, 0))
        draws.update(nonfinite_masks_equal=all(ma), n_finite=int(fin.sum()),
                     max_abs=float(d.max()) if d.size else 0., max_rel=float(rr.max()) if rr.size else 0.,
                     p99_rel=float(np.quantile(rr, .99)) if rr.size else 0.,
                     n_rel_gt_1e_5=int((rr > 1e-5).sum()), median_abs_ref=float(np.median(a)) if a.size else 0.)
        r.maxabs = max(r.maxabs, draws['max_abs']); r.maxrel = max(r.maxrel, draws['max_rel']); r.n += draws['n_finite']
    else:
        r.structure.append('bootstrap_draws.npy shape differs')
    worst = sorted(r.worst, reverse=True)[:15]
    ok_tables = all(v.startswith('identical') for v in files.values())
    conclusions_identical = not (r.discrete or r.structure or r.sign or r.ci0) and ok_tables and draws.get('nonfinite_masks_equal', False)
    rep = {'reference': str(ref), 'candidate': str(cand),
           'json_floats_compared': json_n, 'json_max_abs': json_abs, 'json_max_rel': json_rel,
           'draws': draws, 'overall_floats_compared': r.n, 'overall_max_abs': r.maxabs, 'overall_max_rel': r.maxrel,
           'worst_json_values': [dict(rel=w[0], abs=w[1], path=w[2], ref=w[3], cand=w[4]) for w in worst],
           'tables': files, 'n_estimates_sign_checked': r.nest, 'estimate_sign_flips': r.sign,
           'n_cis_checked': r.nci, 'ci_zero_crossing_or_sign_changes': r.ci0,
           'discrete_mismatches_(bool/str/int/gates)': r.discrete[:50], 'n_discrete_mismatches': len(r.discrete),
           'structure_mismatches': r.structure[:50],
           'conclusions_identical': conclusions_identical,
           'criterion': 'user tolerance rule: max rel <= 1e-5 and conclusions identical (NOT the strict 1e-12+1e-10*|ref| gate of lowmem_compare)',
           'equivalent': bool(conclusions_identical and r.maxrel <= 1e-5)}
    print(json.dumps(rep, indent=1, default=str))
    return 0 if rep['equivalent'] else 3

if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
