"""Local synthetic timing, descriptive decomposition, not causal mediation."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import time

import numpy as np
from threadpoolctl import threadpool_limits

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reference', type=Path, required=True)
parser.add_argument('--full-reference', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('boost_benchmark', Path(__file__).resolve().parents[1]/'tactics_code'/'boost_mediation.py')
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)
prior = json.loads(args.reference.read_text())['details']
series_count = prior['inventory']['val_series']
feature_count = len(prior['nuisances']['feature_names'])
full = json.loads(args.full_reference.read_text())['details']
# Possession adds its fixed touch/velocity/half controls to full initiation.
full_features = len(full['nuisances']['feature_names']) + len(bm.possession.TOUCH_LEVELS) + 2
base = bm.synthetic_fixture()
rows_per_series = len(base[0])//len(np.unique(base[4]))
n = series_count*rows_per_series
rng = np.random.default_rng(bm.SEED)
x = rng.uniform(-1, 1, (n, feature_count))
a = rng.binomial(1, .5+.15*x[:, 0])
m = 40+base[-1]['a']*a+3*x[:, 0]+rng.uniform(-15, 15, n)
y = rng.binomial(1, .30+base[-1]['direct']*a+base[-1]['b']*(m-40)+.04*x[:, 0])
started = time.perf_counter()
with threadpool_limits(limits=1):
    result, _ = bm.fit_decomposition(a, m, y, x, np.repeat(np.arange(series_count), rows_per_series))
wall = time.perf_counter()-started
timing = prior['timing_seconds']
ratio = prior['inventory']['development_replays']/prior['selected_replay_count']
# Explicit planning margins, not measurements or speed claims about a target CPU.
assumptions = {'effective_anchor_workers': 12, 'extra_endpoint_work_multiplier': 2.,
               'mac_to_batch_inference_multiplier': 4., 'overall_safety_multiplier': 1.6,
               'environment_allowance_seconds': 15*60, 'round_up_minutes': 10}
dimension_factor = ((full_features+3)/(feature_count+3))**3
projected = (timing['inventory'] + ratio*(timing['events'] +
             timing['anchors']*assumptions['extra_endpoint_work_multiplier']/assumptions['effective_anchor_workers']) +
             wall*dimension_factor*assumptions['mac_to_batch_inference_multiplier'])
budget = projected*assumptions['overall_safety_multiplier']+assumptions['environment_allowance_seconds']
minutes = int(np.ceil(budget/(60*assumptions['round_up_minutes']))*assumptions['round_up_minutes'])
report = {'label': bm.LABEL, 'synthetic_only': True, 'reference_source': str(args.reference),
          'full_feature_source': str(args.full_reference), 'full_feature_count': full_features,
          'conservative_cubic_dimension_multiplier': dimension_factor,
          'machine': platform.platform(), 'rows': n, 'series': series_count, 'features': feature_count,
          'bootstrap_repeats': bm.BOOTSTRAP, 'seed': bm.SEED, 'wall_seconds': wall,
          'fit_timing_seconds': result['timing_seconds'], 'source_timing_seconds': timing,
          'source_replays': prior['selected_replay_count'], 'target_replays': prior['inventory']['development_replays'],
          'assumptions': assumptions, 'projected_compute_seconds': projected,
          'budget_seconds': budget, 'slurm_minutes': minutes,
          'slurm_time': f'{minutes//60:02d}:{minutes%60:02d}:00',
          'caveat': 'Projection only: prior replay extraction timing plus synthetic regression timing; no full replay run.'}
bm.dr.atomic_json(args.out, report)
print(json.dumps(report, indent=2))
