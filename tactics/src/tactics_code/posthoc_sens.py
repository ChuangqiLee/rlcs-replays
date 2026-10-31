"""POST-HOC sensitivity analyses (not preregistered; labelled as such in every output).
S1: P5 L1/L2 restricted to natively validated replays (measurement gate repair).
S2: P6.2 K2 with score_diff clipped to [-c, c] so whole-series bootstrap draws are full rank.
Reads only existing 2025-val artifacts; never touches 2026."""
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd

def s1(p5_art):
    from tactics_code import rotation_latency as rl
    losses = pd.read_parquet(p5_art / 'losses.parquet')
    reps = pd.read_parquet(p5_art / 'replay_events.parquet')
    ok = set(reps.loc[reps.validated.eq(True), 'replay_id'])
    sub = losses.loc[losses.replay_id.isin(ok)].copy()
    res = rl.analyze(sub, False)
    return dict(n_losses_all=len(losses), n_losses_validated=len(sub),
                n_replays_validated=len(ok), n_replays_all=int(reps.replay_id.nunique()), result=res)

def s2(kick_art, clips):
    from tactics_code import kickoff as k
    units = pd.read_parquet(kick_art / 'val' / 'kickoff_units.parquet')
    frozen = json.loads((kick_art / 'train_thresholds.json').read_text())
    out = {}
    for c in clips:
        u = units.copy(); u['score_diff'] = u['score_diff'].clip(-c, c)
        out[f'clip{c}'] = k.secondary(u, frozen)
    return dict(n_units=len(units), score_diff_counts={str(a): int(b) for a, b in units['score_diff'].value_counts().items()}, by_clip=out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--p5-artifacts', type=Path, required=True)
    ap.add_argument('--kickoff-artifacts', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    r = dict(label='POST-HOC sensitivity; not preregistered; not finding-eligible on its own', split='val-2025')
    try: r['S1_p5_validated_only'] = s1(a.p5_artifacts)
    except Exception as e: r['S1_p5_validated_only'] = dict(error=repr(e))
    try: r['S2_k2_score_clip'] = s2(a.kickoff_artifacts, [3, 2])
    except Exception as e: r['S2_k2_score_clip'] = dict(error=repr(e))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(r, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    print('wrote', a.out)
main()
