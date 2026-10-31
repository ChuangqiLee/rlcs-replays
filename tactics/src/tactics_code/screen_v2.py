"""Pragmatic B01--B18 development SCREEN, never final confirmation.

TRAIN seasons fit nuisance models, reference distributions and thresholds;
2025 supplies statistics. Only allowlisted compact/native paths are opened.
Use --smoke on login nodes (10 replays, one worker). Full run requires Slurm.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import pickle
import shutil
import tempfile
import time

for _thread_variable in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS',
                         'BLIS_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_thread_variable]='1'
import numpy as np
import pandas as pd

from . import screen as old
from . import events
from .common import atomic_json, now, clean

TRAIN_SEASONS=old.TRAIN_SEASONS
VAL_SEASON=old.VAL_SEASON
ALLOWED_SEASONS=old.ALLOWED_SEASONS
IDS=old.IDS
guard_path=old.guard_path
DEFAULT_INPUT=Path('artifacts/p3-small-41104745-s42-w6-f10-ksweep/compact')


# Extraction fragment for screen_v2.py. Imports expected: np, pd, Path, old.


def _v2_event_context(goals, certification):
    """Validated native event clock; timestamps are first post-goal frames."""
    cert = certification or {}
    valid = bool(cert.get("validated", False))
    records = sorted((g for g in goals if bool(g.get("validated", False))), key=lambda g: float(g["time"]))
    # Do not silently drop an invalid goal and manufacture complete follow-up.
    valid = valid and len(records) == len(goals)
    gaps0 = np.asarray(old.parsed_json(cert.get("gap_start_times"), []), float)
    gaps1 = np.asarray(old.parsed_json(cert.get("gap_end_times"), []), float)
    return dict(valid=valid, goals=records, times=np.asarray([float(g["time"]) for g in records]),
                gaps0=gaps0, gaps1=gaps1, cert=cert)


def _v2_followup(c, i, horizon, event_context):
    """First goal/terminal or complete native follow-up; otherwise censor.

    Returns event dict (possibly None), stop time, reason. An unknown compact
    reset before the first goal/verified terminal also censors the observation.
    The goal itself is never required to survive compact live-window filtering.
    """
    ec, start = event_context, float(c.t[i])
    if not ec["valid"]:
        return None, None, "native_goal_timeline_not_validated"
    cert, end = ec["cert"], start + horizon
    terminal = cert.get("terminal_time")
    terminal = float(terminal) if terminal is not None and pd.notna(terminal) and cert.get("terminal_verified") else np.inf
    end = min(end, terminal)
    if end < start:
        return None, None, "anchor_after_certified_terminal"
    pos = int(np.searchsorted(ec["times"], start, side="right"))
    goal = ec["goals"][pos] if pos < len(ec["goals"]) and ec["times"][pos] <= end+1e-7 else None
    # A native timing bracket overlapping the anchor is not known prospective.
    if goal is not None and float(goal["last_live_time"]) < start-1e-7:
        return None, None, "anchor_inside_goal_timing_bracket"
    stop = float(goal["time"]) if goal is not None else end
    observed_end = float(cert.get("observed_end_time", -np.inf))
    if stop > observed_end+1e-7:
        return None, None, "truncated_native_followup"
    if np.any((ec["gaps0"] < stop) & (ec["gaps1"] > start)):
        return None, None, "native_gap_in_followup"
    # Compact's terminal may precede the first post-goal native stamp by <.1s.
    check_stop = float(goal["last_live_time"]) if goal is not None else stop
    before = np.flatnonzero((c.t >= start) & (c.t < check_stop-1e-7))
    if len(before) and (np.any(c.a["segment"][before] != c.a["segment"][i]) or
                        not np.all(c.a["live"][before]) or np.any(np.diff(c.t[before]) > .160001)):
        return None, None, "unknown_compact_reset_before_outcome"
    if check_stop > float(c.t[-1])+.160001 and goal is None and terminal > stop+1e-7:
        return None, None, "truncated_compact_followup"
    return goal, stop, None


def _v2_concession(c, i, ec, horizon=3.):
    goal, stop, reason = _v2_followup(c, i, horizon, ec)
    if reason:
        return None, reason
    return int(goal is not None and int(goal["scoring_team"]) != int(c.m["focal_team"])), None


def _v2_ball_path(c, i, horizon, ec):
    """Ball-y path through first goal, then absorb at the analysis goal line.

    Certified non-goal game end is absorbing at the final live ball position.
    Only ball validity is required after baseline (not future car availability).
    """
    goal, stop, reason = _v2_followup(c, i, horizon, ec)
    if reason:
        return None, None, reason
    start = float(c.t[i])
    last_time = float(goal["last_live_time"]) if goal is not None else stop
    indices = np.flatnonzero((c.t >= start-1e-7) & (c.t <= last_time+1e-7) &
                             (c.a["segment"] == c.a["segment"][i]) & c.a["live"].astype(bool))
    if not len(indices):
        return None, None, "missing_ball_path"
    tt, yy = np.asarray(c.t[indices], float), np.asarray(c.a["ball"][indices, 1], float)
    if not np.isfinite(yy).all() or np.any(np.diff(tt) > .160001):
        return None, None, "invalid_ball_path"
    if tt[-1] < last_time-.160001:
        return None, None, "missing_ball_path_tail"
    if goal is not None:
        boundary = 5120. if int(goal["scoring_team"]) == int(c.m["focal_team"]) else -5120.
        tt = np.r_[tt, float(goal["time"]), start+horizon]
        yy = np.r_[yy, boundary, boundary]
    else:
        terminal = ec["cert"].get("terminal_time")
        absorbed = bool(ec["cert"].get("terminal_verified")) and terminal is not None and float(terminal) <= start+horizon+1e-7
        if not absorbed:
            # Interpolate the end only from neighboring same-segment live rows.
            right = int(np.searchsorted(c.t, start+horizon, side="left"))
            if right >= len(c.t):
                return None, None, "missing_ball_endpoint"
            if (c.a["segment"][right] != c.a["segment"][i] or not c.a["live"][right] or
                    float(c.t[right])-tt[-1] > .160001 or not np.isfinite(c.a["ball"][right, 1])):
                return None, None, "unknown_ball_endpoint_reset"
            end_y = float(np.interp(start+horizon, [tt[-1], float(c.t[right])], [yy[-1], float(c.a["ball"][right, 1])]))
        else:
            end_y = float(yy[-1])
        tt, yy = np.r_[tt, start+horizon], np.r_[yy, end_y]
    return tt, yy, None


def _v2_B09(c, ec, exclusions):
    rows, velocity = [], old._late_velocity(c)
    for i in old._late_reversals(c):
        # Only exposure .4s must remain live; outcomes may terminate in a goal.
        if not c.ok(i, .4, .4):
            continue
        tt, yy, reason = _v2_ball_path(c, i, 2.5, ec)
        if reason:
            exclusions["B09:"+reason] = exclusions.get("B09:"+reason, 0)+1
            continue
        j = c.idx(i, .4)
        dv = velocity[j, :3, 1]-velocity[i, :3, 1]
        half = float(np.interp(float(c.t[i])+.5, tt, yy))
        future = yy[tt >= float(c.t[i])+.5-1e-7]
        excursion = max(0., half-float(min(np.min(future), half)))
        rear = int(np.argmin(c.a["players"][i, :3, 1]))
        rows.append(c.row(i, x=float(np.std(dv)), y=excursion,
            diversity=float(np.std(dv)), mean_delta_vy=float(np.mean(dv)),
            initial_vy=velocity[i, :3, 1].tolist(), rear_delta_vy=float(dv[rear]),
            reversal_magnitude=float(c.a["ball"][c.idx(i, -.3), 4]-c.a["ball"][j, 4]),
            goal_absorbed=bool(np.any(ec["times"] > c.t[i]) and
                np.any((ec["times"] > c.t[i]) & (ec["times"] <= c.t[i]+2.5)))))
    return rows


def _v2_B17(c, ec, exclusions):
    rows = old.B17(c)
    kept = []
    for row in rows:
        tt, yy, reason = _v2_ball_path(c, row["index"], 2., ec)
        if reason:
            exclusions["B17:"+reason] = exclusions.get("B17:"+reason, 0)+1
            # References concern current shapes, not future observability.
            # Retain these anchors for the 2024 reference, then filter missing
            # outcomes only in the progress regression.
            row["y"] = None
            row["outcome_censor_reason"] = reason
        else:
            row["y"] = float(yy[-1]-yy[0])
        kept.append(row)
    return kept


def _v2_controls(row, idea):
    """Fixed physical scales and bins; no fit or cutoff is learned from val.

    Full current coordinates are omitted for geometric exposures B02/03/06/07/
    12/13/17/18, whose named summaries avoid algebraically removing the effect.
    Categorical region/season/roster/opponent are encoded by the training fitter.
    """
    ball, players = np.asarray(row["ball"], float), np.asarray(row["players"], float)
    bs, ps = np.array([4096,5120,2044,2300,2300,2300]), np.array([4096,5120,2044,2300,2300,2300,255])
    remaining = float(row["remaining"])/300.
    values = [float(row["score_diff"]), remaining, remaining**2, float(row["overtime"]),
              float(row["ot_duration"])/300., min(float(row["segment_age"]), 120.)/120.,
              float(row["score_diff"] < 0), float(row["score_diff"] > 0),
              float(row["remaining"] <= 60), float(row["remaining"] <= 120)]
    values.extend(ball/bs)
    values.extend([float(ball[1] < -1707), float(-1707 <= ball[1] < 0),
                   float(0 <= ball[1] < 1707), float(ball[2] < 300), float(300 <= ball[2] < 800),
                   float(abs(ball[0]) > 3000)])
    past = np.asarray(row["past_ball"], float)
    if past.ndim != 2 or len(past) == 0:
        past = ball[None, :]
    # The y-history is B02's exposure; adjust x/z history and current full ball.
    columns = [0, 2, 3, 5] if idea == "B02" else list(range(6))
    values.extend(past[:, columns].mean(axis=0)/bs[columns])
    values.extend((past[-1, columns]-past[0, columns])/bs[columns])
    if idea == "B18":
        # Sectors are the endpoint: no evaluated player's relative xy appears.
        values.extend(players[:, 2:7].mean(axis=0)/ps[2:7])
        values.extend(np.linalg.norm(players[:, 3:5], axis=1)/2300.)
        values.extend(players[:, 6]/255.)
    elif idea in {"B02", "B03", "B06", "B07", "B12", "B13", "B17"}:
        values.extend(players[:3].mean(axis=0)/ps)
        if idea not in {"B02", "B07"}:
            values.extend(np.ptp(players[:3, :2], axis=0)/ps[:2])
        values.extend(players[:3, 2]/2044.)
        values.extend(players[:3, 6]/255.)
        # Geometry B is a function of both teams: use opponent summaries for B03.
        if idea == "B03":
            values.extend(players[3:].mean(axis=0)/ps)
            values.extend(np.ptp(players[3:, :2], axis=0)/ps[:2])
        else:
            values.extend((players[3:]/ps).ravel())
    else:
        values.extend((players/ps).ravel())
    extras = {
        "B02": [("earlier_width", 8192.)],
        "B03": [("A", 1.), ("nearest_defender", 2500.), ("goal_side", 3.)],
        "B06": [("ball_circulation", 1.), ("left_occupancy", 1.), ("rms_radius", 3000.)],
        "B07": [("min_tau", 5.), ("mean_distance", 2500.), ("mean_speed", 2300.)],
        "B09": [("mean_delta_vy", 2300.), ("reversal_magnitude", 4600.), ("rear_delta_vy", 2300.)],
        "B10": [("initial_clearance", 2000.), ("pretrend", 2000.), ("departing_distance_change", 2500.)],
        "B11": [("elapsed_approach", 5.), ("initial_opponent_toward", 2300.), ("pre_opponent_acceleration", 2300.)],
        "B12": [("nearest_defender", 2500.), ("goal_side_count", 3.), ("uncovered_grid_fraction", 1.),
                   ("ball_heading", np.pi), ("ball_speed", 4600.)],
        "B13": [("current_area", 1e7)],
        "B14": [("ball_impulse", 4600.)],
        "B15": [("own_period", 4.), ("opponent_period", 4.), ("own_pulse_count", 10.),
                   ("opponent_pulse_count", 10.), ("own_pulse_now", 1.)],
        "B16": [("actual_turn_delta_x", 1000.), ("opponent_start_vx", 2300.), ("prealigned", 1.), ("ending", 1.)],
        "B17": [("width", 8192.), ("depth", 10240.)],
    }
    for key, scale in extras.get(idea, []):
        values.append(float(row[key])/scale)
    if idea == "B04":
        for key, scale in (("teammate_distances", 5000.), ("opponent_distances", 5000.),
                           ("teammate_speeds", 2300.), ("opponent_speeds", 2300.)):
            values.extend(np.asarray(row[key])/scale)
    if idea == "B05":
        values.extend(np.asarray(row["initial_distances"])/2500.)
        values.append(float(row["distance_gap"])/200.)
    if idea == "B08":
        history = np.asarray(row["boost_history"], float)
        values.extend(history.mean(axis=0)/255.)
        values.extend((history[-1]-history[0])/255.)
    if idea == "B09":
        values.extend(np.asarray(row["initial_vy"])/2300.)
    if idea == "B14":
        values.extend(np.asarray(row["reversal_path"])/2300.)
        values.extend(np.asarray(row["starting_vx"])/2300.)
        values.extend(np.asarray(row["y_spacing"])/5120.)
    if idea == "B15":
        values.extend([np.sin(row["own_phase"]), np.cos(row["own_phase"])])
        values.extend(np.asarray(row["own_history"])/12.)
    return np.asarray(values, dtype=np.float32)


def _v2_slim(row, idea, meta, c):
    """Discard bulky duplicated states after extracting adjusted-model features."""
    control_row = row
    if idea == "B11":
        onset = int(np.searchsorted(c.t, row["onset_time"], side="left"))
        # Pre-pause state, never end-of-pause coordinates that encode exposure.
        control_row = dict(row, **{k: v for k, v in c.row(onset).items()
                                  if k in ("ball", "players", "past_ball", "score_diff", "remaining",
                                           "overtime", "ot_duration", "segment_age")})
        row["y"] = row["diagnostic_response"]
    row["controls"] = _v2_controls(control_row, idea)
    # B04 keeps equal-sized sampled trajectory features in both augmented fits.
    if idea == "B04":
        idx = int(row["index"])
        times = np.array([c.idx(idx, -1.), c.idx(idx, -.5), idx])
        focal = int(row["x"])
        own, opp = row["teammate_slots"], row["opponent_slots"]
        row["base_features"] = np.r_[c.a["players"][idx, :, :7].ravel(),
            c.a["players"][times, focal, :7].ravel(), c.a["ball"][times, :6].ravel()].astype(np.float32)
        row["teammate_features"] = c.a["players"][times][:, own, :7].ravel().astype(np.float32)
        row["opponent_features"] = c.a["players"][times][:, opp, :7].ravel().astype(np.float32)
    if idea == "B18":
        ids = old.parsed_json(meta.get("player_ids"), [])
        row["player_ids"] = list(ids[:3]) if isinstance(ids, (list, tuple)) else []
        row["individual_speed"] = np.linalg.norm(c.a["players"][row["index"], :3, 3:5], axis=1).astype(np.float32)
        row["individual_boost"] = c.a["players"][row["index"], :3, 6].astype(np.float32)
    if idea in {"B17", "B18"}:
        b = np.asarray(row["ball"])
        row["reference_context"] = (int(b[1] >= 0), int(b[2] >= 300),
            int(np.sign(row["score_diff"])), int(row["remaining"] <= 60), int(row["overtime"]))
    # Fields needed for secondary diagnostics stay small and explicit.
    discard = {"ball", "players", "past_ball", "past_players", "ball_history", "player_history",
               "receiver_block", "source_block", "realized_ball", "response_block", "initial_state",
               "boost_history", "front_block", "rear_block", "primary_unavailable", "outcome_unavailable",
               "coarse_grid", "baseline_control_exception", "null", "timing_validation"}
    result = {k: v for k, v in row.items() if k not in discard}
    for key, value in tuple(result.items()):
        if isinstance(value, list) and value and not isinstance(value[0], str):
            try:
                array = np.asarray(value)
                if array.dtype.kind in "biuf":
                    result[key] = array.astype(np.float32)
            except (TypeError, ValueError):
                pass
    return result


def process_replay_v2(task):
    """Extract one replay (both perspectives), retaining all 18 screen quantities.

    task = (metadata_pair, seed, mmap_directory_or_None, goal_records, replay_cert)
    Goals are events.py records for this replay only. train_impulses are sampled
    once per replay from valid live consecutive ball-velocity changes (10 Hz).
    """
    pair, seed, mmap_dir, goals, certification = task
    output = {idea: [] for idea in old.IDS}
    exclusions, impulses, boost_audit = {}, np.empty(0, np.float32), {}
    ec = _v2_event_context(goals, certification)
    for perspective, meta in enumerate(pair):
        if meta["season"] not in old.ALLOWED_SEASONS or meta["split"] not in {"train", "val"}:
            raise ValueError("Forbidden season/split before array open")
        if mmap_dir:
            start, stop = int(meta["start"]), int(meta["stop"])
            arrays = {key: np.load(Path(mmap_dir)/(key+".npy"), mmap_mode="r", allow_pickle=False)[start:stop]
                      for key in old.REQUIRED}
        else:
            arrays = old.read_slice(meta)
        c = old.Context(meta, arrays, seed)
        if perspective == 0 and meta["split"] == "train":
            dt = np.diff(c.t)
            good = c.valid[1:] & c.valid[:-1] & (np.diff(arrays["segment"]) == 0) & (dt > 0) & (dt <= .160001)
            dv = np.linalg.norm(np.diff(arrays["ball"][:, 3:6], axis=0), axis=1)
            impulses = dv[good & np.isfinite(dv)].astype(np.float32)
            boost = arrays["players"][:, :, 6]
            boost = boost[np.isfinite(boost)]
            if len(boost):
                top = float(boost.max())
                boost_audit = dict(min=float(boost.min()), max=top, n=int(len(boost)),
                                   at_max=int(np.isclose(boost, top, atol=.001).sum()))
        for idea in old.IDS:
            if idea == "B09":
                rows = _v2_B09(c, ec, exclusions)
            elif idea == "B17":
                rows = _v2_B17(c, ec, exclusions)
            else:
                rows = getattr(old, idea)(c)
            for row in rows:
                if idea in {"B03", "B12", "B13"}:
                    outcome, reason = _v2_concession(c, row["index"], ec)
                    if reason:
                        exclusions[idea+":"+reason] = exclusions.get(idea+":"+reason, 0)+1
                        if idea != "B03":
                            continue
                        # Train brittleness quantiles use baseline geometry,
                        # independently of whether future labels are observed.
                        row["outcome_censor_reason"] = reason
                    row["y"] = outcome
                    row["concession"] = outcome
                if idea == "B14" and not row["stable_order"]:
                    exclusions["B14:unstable_depth_order"] = exclusions.get("B14:unstable_depth_order", 0)+1
                    continue
                slim = _v2_slim(row, idea, meta, c)
                if not np.isfinite(slim["controls"]).all():
                    exclusions[idea+":nonfinite_controls"] = exclusions.get(idea+":nonfinite_controls", 0)+1
                    continue
                output[idea].append(slim)
    return dict(replay_id=pair[0]["replay_id"], rows=output, train_impulses=impulses,
                boost_audit=boost_audit, exclusions=exclusions)

# Statistical core; all nuisance fits and feature scales are train-only.


def _layout(rows, team=False):
    keys = [(str(r['series_id']), str(r.get('roster_id', r.get('focal_team', ''))))
            if team else str(r['series_id']) for r in rows]
    labels = sorted(set(keys))
    lookup = {key: i for i, key in enumerate(labels)}
    index = np.asarray([lookup[k] for k in keys], int)
    return labels, index, np.bincount(index, minlength=len(labels)).astype(float)


def _weights(rows):
    # Equal team-series within series, then equal series.
    series, si, _ = _layout(rows)
    teams, ti, tn = _layout(rows, True)
    per_series = Counter(k[0] for k in teams)
    w = 1. / (tn[ti] * np.asarray([per_series[str(r['series_id'])] for r in rows]))
    return w / w.mean()


def _demean(values, rows):
    values = np.asarray(values, float)
    one = values.ndim == 1
    a = values[:, None] if one else values
    _, ix, counts = _layout(rows, True)
    sums = np.zeros((len(counts), a.shape[1]))
    np.add.at(sums, ix, a)
    out = a - (sums / counts[:, None])[ix]
    return out[:, 0] if one else out


def _cap_train(rows, seed=42, maximum=50000):
    if len(rows) <= maximum:
        return rows
    # Outcome-independent sample; extraction/record order is deterministic.
    ix = old.replicate_rng(seed, 'train_fit_cap', 0, 'rows').choice(len(rows), maximum, replace=False)
    return [rows[i] for i in sorted(ix)]


class FrozenRidge:
    """Train-scaled ridge with sparse, shrinkage roster/opponent/region effects.

    New identity levels receive zero learned offset; no overlap gate. Validation
    association statistics additionally remove team-series means. No val target
    enters this object. Fixed alpha=10, no tuning on the statistic sample.
    """
    def __init__(self, train, targets, extra=None, alpha=10.):
        from scipy import sparse
        from sklearn.preprocessing import OneHotEncoder
        from sklearn.linear_model import Ridge
        self.extra = extra
        a = self.numeric(train)
        self.mean = a.mean(axis=0)
        self.scale = a.std(axis=0)
        self.scale[self.scale < 1e-6] = 1.
        self.encoder = OneHotEncoder(handle_unknown='ignore', sparse_output=True)
        cats = self.encoder.fit_transform(self.categories(train))
        x = sparse.hstack([sparse.csr_matrix((a-self.mean)/self.scale), cats], format='csr')
        self.model = Ridge(alpha=alpha, solver='lsqr', tol=1e-6)
        self.model.fit(x, np.asarray(targets, float), sample_weight=_weights(train))

    def numeric(self, rows):
        base = np.asarray([r['controls'] for r in rows], float)
        if self.extra:
            base = np.column_stack([base, np.asarray([self.extra(r) for r in rows], float)])
        if not np.isfinite(base).all():
            raise ValueError('Nonfinite model inputs')
        return base

    @staticmethod
    def categories(rows):
        return [[str(r.get(k) or 'unknown') for k in ('region', 'season', 'roster_id', 'opponent_roster_id')]
                for r in rows]

    def predict(self, rows):
        from scipy import sparse
        # Bound transient feature matrices on the MEDIUM artifact.
        output = []
        for start in range(0, len(rows), 10000):
            part = rows[start:start+10000]
            x = sparse.hstack([sparse.csr_matrix((self.numeric(part)-self.mean)/self.scale),
                               self.encoder.transform(self.categories(part))], format='csr')
            output.append(self.model.predict(x))
        return np.concatenate(output)


def _missing(rows, reason, **details):
    return dict(effect=None, ci95=[None, None], p=None, n_series=len({r['series_id'] for r in rows}),
                n_events=len(rows), status='not_computable', reason=reason, details=details)


def _interval(effect, draws, null=0.):
    draws = np.asarray(draws, float)
    good = draws[np.isfinite(draws)]
    if len(good) < .9*len(draws) or not len(good):
        return [None, None], None, len(good)
    ci = np.quantile(good, [.025, .975]).tolist()
    if np.ptp(good) < 1e-12:
        # A degenerate cluster distribution cannot establish a discovery.
        return ci, 1., len(good)
    p = (1+np.count_nonzero(np.abs(good-effect) >= abs(effect-null)))/(1+len(good))
    return ci, float(p), len(good)


def _cluster_stat(rows, components, statistic, idea, seed, reps, workers):
    labels, ix, counts = _layout(rows)
    if len(labels) < 2:
        return _missing(rows, 'Fewer than two validation series with measurable events')
    a = np.asarray(components, float)
    if a.ndim == 1:
        a = a[:, None]
    w = _weights(rows)
    sums = np.zeros((len(labels), a.shape[1]))
    np.add.at(sums, ix, a*w[:, None])
    total_w = np.bincount(ix, weights=w, minlength=len(labels))
    averages = sums/total_w[:, None]
    point = float(statistic(averages.mean(axis=0)))
    if not np.isfinite(point):
        return _missing(rows, 'Undefined statistic: zero residual exposure variance or empty denominator')
    def boot(rng):
        return float(statistic(averages[rng.integers(0, len(labels), len(labels))].mean(axis=0)))
    draws = old.replicate_map(boot, reps, seed, idea, 'v2_series', workers)
    ci, p, valid = _interval(point, draws)
    if p is None:
        return _missing(rows, 'More than 10% of whole-series resamples have singular statistic', valid_replicates=valid)
    return dict(effect=point, ci95=ci, p=p, n_series=len(labels), n_events=len(rows), status='computed',
                details=dict(resampling_unit='whole series; both perspectives and all observed games retained',
                    bootstrap_replicates=reps, valid_replicates=valid, series_equal_weight=True,
                    uncertainty='conditional on train-frozen nuisance/reference models',
                    p_method='two-sided centered whole-series bootstrap',
                    independent_series_warning='Shared rosters can correlate distinct series; exploratory SCREEN only'))


def mean_screen(rows, values, idea, seed=42, reps=2000, workers=1):
    return _cluster_stat(rows, values, lambda a: a[0], idea, seed, reps, workers)


def _residuals(train, val, target):
    fitting = _cap_train(train)
    model = FrozenRidge(fitting, [target(r) for r in fitting])
    return np.asarray([target(r) for r in val], float)-model.predict(val)


def regression_screen(train, val, idea, seed=42, reps=2000, workers=1):
    """Train-adjusted within-team-series slope; 0/1 gives an adjusted difference.

    B07 supplies [ambiguous, wide, interaction] and tests only interaction.
    All parameters for nuisance prediction are fixed on training. The validation
    slope is the declared statistic, not a model chosen for validation outcomes.
    """
    if not train or not val:
        return _missing(val, 'No training or validation rows after measurable-event restrictions')
    if idea == 'B07' and {(int(r['ambiguous']),int(r['wide'])) for r in val} != {(0,0),(0,1),(1,0),(1,1)}:
        return _missing(val, 'One or more ambiguity by separation cells has no validation events')
    x = lambda r: [r['ambiguous'], r['wide'], r['ambiguous']*r['wide']] if idea == 'B07' else r['x']
    y = lambda r: r['y']
    raw_x = np.asarray([x(r) for r in val], float)
    raw_y = np.asarray([y(r) for r in val], float)
    if not np.isfinite(raw_y).all() or np.ptp(raw_y)<1e-12:
        return _missing(val, 'Validation outcome is constant or nonfinite; no observed outcome variation')
    if (raw_x.ndim == 1 and np.ptp(raw_x) < 1e-12) or not np.isfinite(raw_x).all():
        return _missing(val, 'Validation exposure is constant or nonfinite; no contrast is observed')
    rx = _demean(_residuals(train, val, x), val)
    ry = _demean(_residuals(train, val, y), val)
    if rx.ndim == 1:
        if np.mean(rx**2) < 1e-12:
            return _missing(val, 'No within-team-series exposure variation after train adjustment')
        comp = np.column_stack([rx*ry, rx*rx])
        statistic = lambda a: a[0]/a[1] if a[1] > 1e-12 else np.nan
    else:
        if np.linalg.matrix_rank(rx) < 3:
            return _missing(val, 'Ambiguity/separation interaction has deficient observed cell support')
        comp = np.column_stack([(rx[:, :, None]*rx[:, None, :]).reshape(len(rx), -1), rx*ry[:, None]])
        def statistic(a):
            m = a[:9].reshape(3, 3)
            return np.linalg.solve(m, a[9:])[2] if np.linalg.cond(m) < 1e10 else np.nan
    result = _cluster_stat(val, comp, statistic, idea, seed, reps, workers)
    result['details'].update(adjustment='train ridge; ball bins/state/history, score, clock, region and idea controls; within-team-series centering',
        training_events=len(train), fitting_events=min(len(train), 50000),
        train_exposure_range=[float(np.min([r['x'] for r in train])), float(np.max([r['x'] for r in train]))])
    if raw_x.ndim == 1 and set(np.unique(raw_x)) <= {0, 1}:
        result['details']['arm_counts'] = {str(k):dict(events=int(np.sum(raw_x == k)),
            series=len({r['series_id'] for r, v in zip(val, raw_x) if v == k})) for k in (0, 1)}
    return result


def gain_screen_v2(train, val, idea, seed, reps, workers):
    if not train or not val:
        return _missing(val, 'No training or validation response blocks')
    rx = _demean(_residuals(train, val, lambda r:r['x']), val)
    ry = _demean(_residuals(train, val, lambda r:r['y']), val)
    sign = -1. if idea == 'B01' else 1.
    result = _cluster_stat(val, np.column_stack([sign*rx*ry, rx*rx]),
                          lambda a: a[0]/a[1] if a[1] > 1e-12 else np.nan, idea, seed, reps, workers)
    if result['p'] is None:
        return result
    _, ti, _ = _layout(val, True)
    blocks = [np.flatnonzero(ti == k) for k in range(ti.max()+1)]
    w = _weights(val)
    denominator = np.dot(w, rx*rx)
    def perm(rng):
        shifted = ry.copy()
        # Each scalar represents a complete measured response event. Circular
        # shifts keep their order and within-series dependence; never frame shuffle.
        for ix in blocks:
            shifted[ix] = np.roll(ry[ix], int(rng.integers(len(ix))))
        return sign*np.dot(w, rx*shifted)/denominator
    null = np.asarray(old.replicate_map(perm, reps, seed, idea, 'v2_within_series_blocks', workers))
    # Exact mean over all circular offsets is zero after team-series centering.
    raw = result['effect']
    result['p'] = float((1+np.sum(np.abs(null) >= abs(raw)))/(1+len(null)))
    result['details'].update(observed_gain=raw, null_expected_gain=0.,
        null_mc_mean=float(null.mean()), null_replicates=reps,
        p_method='two-sided within-team-series circular response-event block permutation',
        exchangeability='approximate after train adjustment; preserves response-block order, not a randomized causal test')
    return result


def _probability(prediction):
    p = np.clip(np.asarray(prediction), .005, .995)
    return p/p.sum(axis=1, keepdims=True) if p.ndim == 2 and p.shape[1] == 3 else p


def prediction_screen_v2(train, val, idea, boost_scale, seed, reps, workers):
    if not train or not val:
        return _missing(val, 'No training or validation prediction events')
    fitting = _cap_train(train)
    if idea == 'B04':
        labels = np.asarray([r['y'] for r in fitting], int)
        yy = np.eye(3)[labels]
        target = np.asarray([r['y'] for r in val], int)
        losses = []
        for side in ('teammate_features', 'opponent_features'):
            model = FrozenRidge(fitting, yy, extra=lambda r, side=side:np.r_[r['base_features'], r[side]])
            p = _probability(model.predict(val))
            losses.append(-np.log2(p[np.arange(len(val)), target]))
        result = mean_screen(val, losses[1]-losses[0], idea, seed, reps, workers)
        result['details'].update(teammate_loss_bits=float(np.average(losses[0], weights=_weights(val))),
            opponent_loss_bits=float(np.average(losses[1], weights=_weights(val))),
            model='identical fixed ridge probability models; equal history dimension; train-only fits')
        return result
    if idea == 'B05':
        yy = np.asarray([r['y'] for r in fitting], float)
        observed = np.asarray([r['y'] for r in val], float)
    else:
        if boost_scale is None:
            return _missing(val, 'Training boost has no finite positive upper scale')
        yy = np.asarray([r['future_boost'] for r in fitting]) < .2*boost_scale
        observed = (np.asarray([r['future_boost'] for r in val]) < .2*boost_scale).astype(float)
    model = FrozenRidge(fitting, yy)
    # These are independent binary marginals, not a three-class softmax.
    prob = np.clip(model.predict(val), .005, .995)
    residual = observed-prob
    if idea == 'B05':
        # Preserve the registered exactly-one minus independent-null quantity.
        actual=(observed.sum(axis=1)==1).astype(float)
        expected=prob[:,0]+prob[:,1]-2*prob[:,0]*prob[:,1]
        excess = actual-expected
        result = mean_screen(val, excess, idea, seed, reps, workers)
        result['details'].update(orthogonal_excess_sensitivity=float(np.average(-2*residual[:,0]*residual[:,1],weights=_weights(val))),
            observed_exactly_one=float(np.average(observed.sum(axis=1) == 1, weights=_weights(val))),
            raw_independent_exactly_one=float(np.average(prob[:,0]+prob[:,1]-2*prob[:,0]*prob[:,1], weights=_weights(val))))
    else:
        pairs = [(0,1),(0,2),(1,2)]
        actual = sum(observed[:,i]*observed[:,j] for i,j in pairs)/3.
        covariance = sum(residual[:,i]*residual[:,j] for i,j in pairs)/3.
        expected = sum(prob[:,i]*prob[:,j] for i,j in pairs)/3.
        result = _cluster_stat(val, np.column_stack([actual,expected]),
            lambda a:a[0]/a[1] if a[1] > 1e-8 else np.nan, idea, seed, reps, workers)
        # Test ratio=1, not ratio=0. Bootstrap p is replaced with centered log-ratio.
        if result['p'] is not None:
            log_result = _cluster_stat(val, np.column_stack([actual,expected]),
                lambda a:np.log(a[0]/a[1]) if min(a)>1e-8 else np.nan,
                idea+'log', seed,reps,workers)
            if log_result['p'] is None:
                return _missing(val, 'Observed/independent pair-risk ratio has zero or nonpositive risk in cluster resamples')
            result['p'] = log_result['p']
            result['details'].update(p_method='centered whole-series bootstrap of log observed/independent pair-risk ratio')
        result['details'].update(absolute_pair_shortage_difference=float(np.average(actual-expected,weights=_weights(val))),
            orthogonal_difference_sensitivity=float(np.average(covariance,weights=_weights(val))),
            observed_pair_risk=float(np.average(actual,weights=_weights(val))),
            independent_pair_risk=float(np.average(expected,weights=_weights(val))), boost_scale=boost_scale)
    result['details'].update(marginal_mean_error=(np.average(residual, axis=0,weights=_weights(val))).tolist(),
        marginal_adjustment='Primary is raw observed minus frozen independent expectation; orthogonal correction is diagnostic only. Marginal miscalibration can mimic coordination.')
    return result


def chirality_screen_v2(train, val, seed, reps, workers):
    from scipy.stats import spearmanr
    if not train or not val:
        return _missing(val, 'No measurable circulation rows')
    # Preserve the focal-roster effect that defines the estimand.
    tr=[dict(r,roster_id='chirality_focal_omitted') for r in train]
    va=[dict(r,roster_id='chirality_focal_omitted') for r in val]
    residual = _residuals(tr, va, lambda r:r['y'])
    # Split series globally, not independently per roster; no series appears in both halves.
    series = sorted({r['series_id'] for r in val},key=lambda s:hashlib.sha256(f'{seed}:{s}'.encode()).digest())
    half = {s:i%2 for i,s in enumerate(series)}
    cells = defaultdict(list)
    for r, y in zip(val,residual):
        cells[(str(r['roster_id']),str(r['series_id']))].append(y)
    rosters = sorted({k[0] for k in cells})
    eligible = [r for r in rosters if {half[s] for rr,s in cells if rr==r} == {0,1}]
    if len(eligible)<3:
        return _missing(val, 'Fewer than three rosters observed in both fixed series halves', rosters_with_both_halves=len(eligible))
    def statistic(multiplicity):
        means=[]
        for r in eligible:
            pair=[]
            for h in (0,1):
                ss=[s for rr,s in cells if rr==r and half[s]==h and multiplicity.get(s,0)>0]
                if not ss:
                    break
                pair.append(np.average([np.mean(cells[r,s]) for s in ss],weights=[multiplicity[s] for s in ss]))
            if len(pair)==2:
                means.append(pair)
        if len(means)<3:
            return np.nan
        a=np.asarray(means)
        return spearmanr(a[:,0],a[:,1]).statistic if min(np.ptp(a,axis=0))>1e-12 else np.nan
    point=statistic(dict.fromkeys(series,1))
    def boot(rng):
        # Stratify bootstrap by fixed halves so the design itself remains fixed.
        counts=Counter()
        for h in (0,1):
            ss=[s for s in series if half[s]==h]
            counts.update(ss[j] for j in rng.integers(len(ss),size=len(ss)))
        return statistic(counts)
    draws=old.replicate_map(boot,reps,seed,'B06','v2_halves',workers)
    ci,p,valid=_interval(point,draws)
    if p is None or not np.isfinite(point):
        return _missing(val, 'Roster split-half correlation undefined in >10% series resamples',eligible_rosters=len(eligible))
    return dict(effect=float(point),ci95=ci,p=p,n_series=len(series),n_events=len(val),status='computed',
        details=dict(eligible_rosters=len(eligible),valid_replicates=valid,training_events=len(train),
        p_method='centered whole-series bootstrap stratified by fixed series halves',
        relaxation='at least one series per roster in each half; no exact opponent match'))


def phase_screen_v2(train, val, seed,reps,workers):
    if not train or not val:
        return _missing(val, 'No episodes with four prior valid pulses per side')
    # Train-frozen nuisance residualization; phase coefficients are the two
    # predeclared validation moments. One joint amplitude test, never peak fishing.
    rx=_demean(_residuals(train,val,lambda r:[np.sin(r['opponent_phase']),np.cos(r['opponent_phase'])]),val)
    ry=_demean(_residuals(train,val,lambda r:r['y']),val)
    if np.linalg.matrix_rank(rx)<2 or len({r['series_id'] for r in val})<2:
        return _missing(val,'No independent series or phase variation for joint sine/cosine statistic')
    w=_weights(val)
    def amplitude(x,weights=w):
        a=x.T@(weights[:,None]*x)
        if np.linalg.cond(a)>1e10:
            return np.nan
        beta=np.linalg.solve(a,x.T@(weights*ry))
        return 2*float(np.linalg.norm(beta))
    observed=amplitude(rx)
    # Whole pulse-history blocks stay intact; one phase rotation per series/team
    # changes relative phase without shuffling individual 0.1s hazard rows.
    _,ti,_=_layout(val,True)
    blocks=[np.flatnonzero(ti==k) for k in range(ti.max()+1)]
    def perm(rng):
        x=rx.copy()
        for ix in blocks:
            angle=rng.uniform(0,2*np.pi)
            rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            x[ix]=rx[ix]@rot
        return amplitude(x)
    null=np.asarray(old.replicate_map(perm,reps,seed,'B15','v2_phase_rotation',workers))
    if not np.isfinite(null).all():
        return _missing(val,'Singular phase design under whole-history rotations')
    correction=float(null.mean())
    comp=np.column_stack([(rx[:,:,None]*rx[:,None,:]).reshape(len(rx),-1),rx*ry[:,None]])
    def statistic(a):
        m=a[:4].reshape(2,2)
        return 2*np.linalg.norm(np.linalg.solve(m,a[4:]))-correction if np.linalg.cond(m)<1e10 else np.nan
    result=_cluster_stat(val,comp,statistic,'B15',seed,reps,workers)
    if result['p'] is not None:
        result['p']=float((1+np.sum(null>=observed))/(1+len(null)))
    result['details'].update(observed_modulation=observed,mean_null_modulation=correction,
        p_method='joint sine/cosine amplitude versus whole-team-series phase rotations',
        ci_caveat='series bootstrap conditional on the fixed permutation mean bias correction',
        units='peak-to-trough change in linear pulse probability per 0.1 s')
    return result


def prepare_area(train,val):
    fitting=_cap_train(train,maximum=5000)
    if not fitting:
        return train,val,{}
    # All 31 log-area targets are modeled using only contemporary TRAIN context.
    from sklearn.linear_model import Ridge
    a=np.concatenate([r['area_context_history'] for r in fitting])
    y=np.concatenate([r['log_area_history'] for r in fitting])
    mu=a.mean(axis=0); sd=a.std(axis=0); sd[sd<1e-6]=1
    model=Ridge(alpha=10.).fit((a-mu)/sd,y)
    transformed=[]
    for collection in (train,val):
        out=[]
        for r in collection:
            e=np.asarray(r['log_area_history'])-model.predict((np.asarray(r['area_context_history'])-mu)/sd)
            if np.std(e)<.05 or min(np.std(e[:-1]),np.std(e[1:]))<1e-8:
                continue
            rho=float(np.corrcoef(e[:-1],e[1:])[0,1])
            copy=dict(r,x=r['concession'],y=rho)
            copy['controls']=np.r_[r['controls'],np.var(e),e[-1]]
            out.append(copy)
        transformed.append(out)
    return *transformed,dict(area_model_training_windows=len(fitting),lag_seconds=.2,history_seconds=6.)


def infer_v2(idea,train,val,thresholds,seed,reps,workers):
    detail={}
    if idea=='B02':
        train=[dict(r,x=int(r['x']>0)) for r in train if r['x']!=0]
        val=[dict(r,x=int(r['x']>0)) for r in val if r['x']!=0]
    elif idea in {'B03','B09'}:
        # Preserve brainstorm TRAIN tertile contrast; no validation optimization.
        if idea=='B09' and train:
            fit=_cap_train(train)
            diversity_model=FrozenRidge(fit,[r['x'] for r in fit])
            train=[dict(r,x=r['x']-v) for r,v in zip(train,diversity_model.predict(train))]
            val=[dict(r,x=r['x']-v) for r,v in zip(val,diversity_model.predict(val))]
        if not train:
            return _missing(val,'No TRAIN exposure distribution to freeze tertile cutoffs')
        lo,hi=np.quantile([r['x'] for r in train],[1/3,2/3])
        if hi<=lo:
            return _missing(val,'TRAIN exposure tertiles coincide')
        thresholds[idea+'_tertiles']=[float(lo),float(hi)]
        detail['train_tertiles']=[float(lo),float(hi)]
        def select(rows):
            return [dict(r,x=int(r['x']>=hi) if idea=='B03' else int(r['x']<=lo))
                    for r in rows if r['x']<=lo or r['x']>=hi]
        train,val=select(train),select(val)
    elif idea=='B11':
        cutoff=thresholds.get('B11_impulse_q95')
        if cutoff is None:
            return _missing(val,'No valid TRAIN ball-velocity increments for impulse cutoff')
        before=len(val)
        train=[r for r in train if r['maximum_ball_impulse']<cutoff]
        val=[r for r in val if r['maximum_ball_impulse']<cutoff]
        detail.update(impulse_cutoff=cutoff,val_impulse_exclusions=before-len(val))
    elif idea=='B13':
        train,val,detail=prepare_area(train,val)
    elif idea=='B17':
        train,val,detail=prepare_rarity(train,val)
    if idea not in {'B05','B08','B18'}:
        train=[r for r in train if r.get('y') is not None and np.isfinite(r['y'])]
        val=[r for r in val if r.get('y') is not None and np.isfinite(r['y'])]
    if idea in {'B01','B14'}:
        result=gain_screen_v2(train,val,idea,seed,reps,workers)
    elif idea in {'B04','B05','B08'}:
        result=prediction_screen_v2(train,val,idea,thresholds.get('boost_scale'),seed,reps,workers)
    elif idea=='B06':
        result=chirality_screen_v2(train,val,seed,reps,workers)
    elif idea=='B15':
        result=phase_screen_v2(train,val,seed,reps,workers)
    elif idea=='B18':
        result=complementarity_screen(train,val,seed,reps,workers)
    else:
        result=regression_screen(train,val,idea,seed,reps,workers)
    result['details'].update(detail)
    if result['p'] is None and detail.get('reason'):
        result['reason']=detail['reason']
    return result

# B17/B18 reference helpers. The assembled module supplies np and old.


def _reference_context(row):
    """Predeclared broad cells, not exact geometry/identity matching."""
    context = tuple(row.get("reference_context", ()))
    if len(context) != 5:
        raise ValueError("B17/B18 require the five recorded reference context bins")
    return (str(row.get("region") or "unknown"),) + context


def _reference_counter_add(table, key, category, n_categories):
    if key not in table:
        table[key] = np.zeros(n_categories, dtype=float)
    table[key][int(category)] += 1.


def prepare_rarity(train, val):
    """B17 opponent-by-shape rarity, with only 2024 as reference.

    All anchors, including censored future trajectories, enter reference
    frequencies. For a target focal roster f, reference rows involving f on
    either side are removed. Opponent o counts consequently subtract only the
    o-versus-f rows. No unsupported opponent is assigned a pooled rarity.

    Fixed screening shrinkage: 20 pseudo-windows for the opponent-wide prior;
    20 opponent-wide plus 20 context-wide pseudo-windows for each local cell.
    These are registered constants, not validation-selected hyperparameters.
    """
    reference = [r for r in train if r.get("season") == "rlcs-2024"]
    detail = dict(reference_season="rlcs-2024", reference_windows=len(reference),
                  uncertainty="Conditional on the frozen 2024 reference distribution",
                  shrinkage_pseudo_windows=dict(opponent=20, local_opponent=20, local_context=20),
                  reference_exclusion="All series involving the evaluated focal roster",
                  unsupported_opponent_policy="Exclude; never identify rarity from pooled prevalence",
                  context="region, ball half/height, score sign, last-minute, overtime")
    if not reference:
        detail.update(reason="No 2024 shape reference anchors", retained_train=0, retained_val=0)
        return [], [], detail
    zero = np.zeros(4, float)
    total, involved, opponent, matchup = {}, {}, {}, {}
    for row in reference:
        shape = int(row["x"])
        if shape not in range(4):
            raise ValueError("Invalid B17 shape")
        ctx, own, opp = _reference_context(row), str(row["roster_id"]), str(row["opponent_roster_id"])
        for key in (None, ctx):
            _reference_counter_add(total, key, shape, 4)
            for roster in {own, opp}:
                _reference_counter_add(involved, (roster, key), shape, 4)
            _reference_counter_add(opponent, (opp, key), shape, 4)
            _reference_counter_add(matchup, (opp, own, key), shape, 4)

    def counts(table, key):
        return table.get(key, zero)

    def transform(rows):
        prepared, excluded, no_context, support, censored = [], 0, 0, [], 0
        for row in rows:
            # Reference counts above include these anchors. Only the payoff
            # statistic excludes a censored/unobserved future ball trajectory.
            if row.get("y") is None or not np.isfinite(float(row["y"])):
                censored += 1
                continue
            ctx, own, opp = _reference_context(row), str(row["roster_id"]), str(row["opponent_roster_id"])
            overall = counts(opponent, (opp, None))-counts(matchup, (opp, own, None))
            if own == opp or overall.sum() <= 0:
                excluded += 1
                continue
            population = counts(total, None)-counts(involved, (own, None))
            population_context = counts(total, ctx)-counts(involved, (own, ctx))
            prior_global = (population+1.)/(population.sum()+4.)
            prior_context = (population_context+20.*prior_global)/(population_context.sum()+20.)
            own_prior = (overall+20.*prior_global)/(overall.sum()+20.)
            local = counts(opponent, (opp, ctx))-counts(matchup, (opp, own, ctx))
            probability = (local+20.*own_prior+20.*prior_context)/(local.sum()+40.)
            if np.any(probability <= 0) or not np.isclose(probability.sum(), 1.):
                raise AssertionError("Invalid frozen B17 reference probability")
            shape = int(row["x"])
            changed = dict(row)
            changed.update(shape=shape, x=float(-np.log2(probability[shape])),
                           reference_probability=float(probability[shape]),
                           reference_n=int(overall.sum()), reference_context_n=int(local.sum()))
            # Shape fixed effects prevent pooled prevalence from masquerading
            # as opponent-specific rarity. Continuous width/depth are retained.
            changed["controls"] = np.r_[row["controls"], np.eye(4)[shape, 1:],
                                        row["width"]/8192., row["depth"]/10240.].astype(np.float32)
            prepared.append(changed)
            no_context += int(local.sum() == 0)
            support.append(float(overall.sum()))
        return prepared, dict(excluded_no_opponent_reference=excluded,
                              excluded_censored_payoff=censored,
                              retained=len(prepared), no_exact_context_reference=no_context,
                              minimum_reference_windows=min(support, default=0),
                              median_reference_windows=float(np.median(support)) if support else 0.)

    newtrain, train_audit = transform(train)
    newval, val_audit = transform(val)
    detail.update(train_support=train_audit, val_support=val_audit,
                  retained_train=len(newtrain), retained_val=len(newval),
                  reference_opponents=len({str(r["opponent_roster_id"]) for r in reference}),
                  supported_validation_opponents=len({str(r["opponent_roster_id"]) for r in newval}))
    if not newval:
        detail["reason"] = "No validation opponent has a 2024 reference after excluding focal-roster series"
    elif detail["supported_validation_opponents"] < 2 or len({r["shape"] for r in newval}) < 2:
        detail["reason"] = "Fewer than two supported validation opponents or shapes; opponent-by-shape rarity is unidentified"
        newval = []
    return newtrain, newval, detail


def _distinct_sector_probability(probabilities):
    """P(three distinct sectors) under the three conditional marginals."""
    a, b, c = np.asarray(probabilities, float)
    return float(1.-np.dot(a, b)-np.dot(a, c)-np.dot(b, c)+2.*np.sum(a*b*c))


def _reference_interval(effect, draws):
    values = np.asarray(draws, float)
    values = values[np.isfinite(values)]
    if not len(values):
        return dict(ci95=[None, None], p=None, valid_replicates=0)
    ci = np.quantile(values, [.025, .975]).tolist()
    p = (1.+np.count_nonzero(np.abs(values-effect) >= abs(effect)))/(len(values)+1.)
    # A degenerate empirical distribution is not evidence of certainty.
    if np.ptp(values) < 1e-12:
        p = 1.
    return dict(ci95=ci, p=float(p), valid_replicates=len(values))


def complementarity_screen(train, val, seed=42, reps=2000, workers=1):
    """B18 independent-trio complementarity from other-roster 2024 habits.

    The screen conditions on trained marginal habits and uses broad context
    strata with fixed shrinkage, not exact player/opponent matched pools.
    Every retained member must have actual other-roster 2024 observations.
    Whole-series and shared-player/roster sensitivity intervals are combined by
    their hull, and the larger p-value is the single B18 BH input.
    """
    from collections import defaultdict
    reference = [r for r in train if r.get("season") == "rlcs-2024"]
    detail = dict(reference_season="rlcs-2024", reference_windows=len(reference),
                  candidate_validation_windows=len(val),
                  uncertainty="Conditional on frozen 2024 marginal fits; target shared-player/roster sensitivity included",
                  reference_exclusion="For each player, exclude every reference observation in the target roster",
                  shrinkage_pseudo_windows=dict(player=20, local_player=20, local_context=20),
                  estimand="Equal target rosters; equal series within each roster; complete series resampling",
                  context="region, ball half/height, score sign, last-minute, overtime, player speed/boost tertiles")

    def missing(reason, count=0, series=0):
        return dict(effect=None, ci95=[None, None], p=None, n_events=count,
                    n_series=series, status="not_computable", reason=reason, details=detail)

    if not reference:
        return missing("No 2024 player-sector reference observations")
    speed = np.asarray([float(v) for r in reference for v in r["individual_speed"]])
    boost = np.asarray([float(v) for r in reference for v in r["individual_boost"]])
    speed_cuts, boost_cuts = np.quantile(speed, [1/3, 2/3]), np.quantile(boost, [1/3, 2/3])
    detail.update(train_speed_tertiles=speed_cuts.tolist(), train_boost_tertiles=boost_cuts.tolist())
    zero = np.zeros(6, float)
    population, population_roster, player, player_roster = {}, {}, {}, {}
    reference_series = defaultdict(set)

    def resource_context(row, member):
        return _reference_context(row)+(int(np.searchsorted(speed_cuts, row["individual_speed"][member])),
                                        int(np.searchsorted(boost_cuts, row["individual_boost"][member])))

    for row in reference:
        roster = str(row["roster_id"])
        ids = row.get("player_ids", [])
        if len(ids) != 3 or len(set(map(str, ids))) != 3:
            raise ValueError("B18 requires three distinct stable own-player IDs")
        for j, pid in enumerate(ids):
            pid, sector = str(pid), int(row["sectors"][j])
            if sector not in range(6):
                raise ValueError("Invalid B18 sector")
            reference_series[(pid, roster)].add(str(row["series_id"]))
            for ctx in (None, resource_context(row, j)):
                _reference_counter_add(population, ctx, sector, 6)
                _reference_counter_add(population_roster, (roster, ctx), sector, 6)
                _reference_counter_add(player, (pid, ctx), sector, 6)
                _reference_counter_add(player_roster, (pid, roster, ctx), sector, 6)

    def counts(table, key):
        return table.get(key, zero)

    retained, differences, probabilities, excluded = [], [], [], 0
    exact_context_missing, reference_ns = 0, []
    for row in val:
        roster, ids = str(row["roster_id"]), list(map(str, row.get("player_ids", [])))
        if len(ids) != 3 or len(set(ids)) != 3:
            excluded += 1
            continue
        p = []
        ns, missing_context = [], 0
        for j, pid in enumerate(ids):
            own = counts(player, (pid, None))-counts(player_roster, (pid, roster, None))
            if own.sum() <= 0:
                break
            ctx = resource_context(row, j)
            pooled = counts(population, None)-counts(population_roster, (roster, None))
            pooled_ctx = counts(population, ctx)-counts(population_roster, (roster, ctx))
            prior_global = (pooled+1.)/(pooled.sum()+6.)
            prior_context = (pooled_ctx+20.*prior_global)/(pooled_ctx.sum()+20.)
            prior_player = (own+20.*prior_global)/(own.sum()+20.)
            local = counts(player, (pid, ctx))-counts(player_roster, (pid, roster, ctx))
            probability = (local+20.*prior_player+20.*prior_context)/(local.sum()+40.)
            if np.any(probability <= 0) or not np.isclose(probability.sum(), 1.):
                raise AssertionError("Invalid frozen B18 player probability")
            p.append(probability)
            ns.append(float(own.sum()))
            missing_context += int(local.sum() == 0)
        if len(p) != 3:
            excluded += 1
            continue
        expected = _distinct_sector_probability(p)
        if not -1e-10 <= expected <= 1.+1e-10:
            raise AssertionError("Invalid independent-trio probability")
        retained.append(row)
        exact_context_missing += missing_context
        probabilities.append(expected)
        differences.append(float(row["observed_complementarity"])-expected)
        reference_ns.extend(ns)
    detail.update(excluded_no_three_member_reference=excluded,
                  retained_validation_windows=len(retained),
                  retained_member_cells_without_exact_context=exact_context_missing,
                  minimum_other_roster_reference_windows=min(reference_ns, default=0),
                  median_other_roster_reference_windows=float(np.median(reference_ns)) if reference_ns else 0.)
    if not retained:
        return missing("No validation trio has other-roster 2024 reference observations for all three players")
    series = sorted({str(r["series_id"]) for r in retained})
    rosters = sorted({str(r["roster_id"]) for r in retained})
    players = sorted({str(p) for r in retained for p in r["player_ids"]})
    detail.update(n_rosters=len(rosters), n_players=len(players))
    if len(series) < 2 or len(rosters) < 2:
        return missing("Fewer than two series or two target rosters with three-member 2024 reference support", len(retained), len(series))
    si, ri, pi = ({key:i for i,key in enumerate(values)} for values in (series, rosters, players))
    values, observed, expected, counts_matrix = (np.zeros((len(rosters), len(series))) for _ in range(4))
    members = {}
    for row, difference, probability in zip(retained, differences, probabilities):
        r, s = ri[str(row["roster_id"])], si[str(row["series_id"])]
        values[r, s] += difference
        observed[r, s] += float(row["observed_complementarity"])
        expected[r, s] += probability
        counts_matrix[r, s] += 1.
        member_indices = tuple(sorted(pi[str(p)] for p in row["player_ids"]))
        if r in members and members[r] != member_indices:
            raise ValueError("A B18 roster ID maps to inconsistent player identities")
        members[r] = member_indices
    mask = counts_matrix > 0
    for matrix in (values, observed, expected):
        np.divide(matrix, counts_matrix, out=matrix, where=mask)

    def statistic(weights, roster_weights=None, matrix=values):
        denominator = mask@weights
        keep = denominator > 0
        if not np.any(keep):
            return np.nan
        means = (matrix@weights)[keep]/denominator[keep]
        rw = np.ones(len(rosters)) if roster_weights is None else roster_weights
        return float(np.average(means, weights=rw[keep])) if np.sum(rw[keep]) > 0 else np.nan

    ones = np.ones(len(series))
    effect = statistic(ones)
    def bootstrap(rng):
        weights = rng.multinomial(len(series), np.full(len(series), 1./len(series)))
        return statistic(weights)
    def crossed(rng):
        weights = rng.multinomial(len(series), np.full(len(series), 1./len(series)))
        # Positive shared multipliers avoid collapsing scarce supported trios.
        # They are a Bayesian pigeonhole sensitivity, not extra independent rows.
        player_weights = rng.exponential(size=len(players))
        roster_weights = rng.exponential(size=len(rosters))
        roster_weights *= np.asarray([np.prod(player_weights[list(members[r])]) for r in range(len(rosters))])
        return statistic(weights, roster_weights)
    draws = old.replicate_map(bootstrap, reps, seed, "B18", "series", workers)
    crossed_draws = old.replicate_map(crossed, reps, seed, "B18", "shared-player-roster", workers)
    primary, sensitivity = _reference_interval(effect, draws), _reference_interval(effect, crossed_draws)
    if primary["p"] is None or sensitivity["p"] is None:
        return missing("All target-series or shared-player resamples are undefined", len(retained), len(series))
    detail.update(observed_complementarity=statistic(ones, matrix=observed),
                  independent_trio_complementarity=statistic(ones, matrix=expected),
                  series_inference=primary, shared_player_roster_inference=sensitivity,
                  positive_roster_fraction=float(np.mean(values.sum(axis=1)/mask.sum(axis=1) > 0)),
                  dependency_method="Whole-series multinomial weights crossed with positive shared-player and roster exponential multipliers; max p and CI hull")
    return dict(effect=effect, ci95=[min(primary["ci95"][0], sensitivity["ci95"][0]),
                                    max(primary["ci95"][1], sensitivity["ci95"][1])],
                p=max(primary["p"], sensitivity["p"]), n_series=len(series),
                n_events=len(retained), status="computed", reason=None, details=detail)

def run_acceptance(datasets=80, reps=199):
    """Exercise the actual estimator on clustered nulls/plants and two workers.

    This is a fixed simulation experiment, not a search for favorable seeds.
    It opens no replay arrays. All nuisance inputs and treatment definitions
    match the ordinary regression_screen interface used by B02 and B10.
    """
    import importlib
    import inspect
    import json
    from pathlib import Path
    import subprocess
    import tempfile
    import time

    import numpy as np
    from scipy.stats import kstest

    module = (importlib.import_module("tactics_code.screen_v2")
              if "regression_screen" not in globals() else None)
    namespace = vars(module) if module is not None else globals()
    estimate = namespace["regression_screen"]
    guard = namespace["guard_path"]
    if datasets < 40 or reps < 99:
        raise ValueError("Calibration requires at least 40 independent datasets and 99 replicates")
    started = time.perf_counter()

    def generate(seed, effect, idea):
        rng = np.random.default_rng(seed)
        output = []
        for split, count in (("train", 40), ("val", 28)):
            rows = []
            for cluster in range(count):
                cluster_error = rng.normal(0, 130)
                covariate_center = rng.normal(0, .6)
                residual = rng.normal(0, 80)
                # Entire series remains intact during inference. Correlated
                # outcomes invalidate naive frame-wise standard errors.
                for event in range(16):
                    z = covariate_center + rng.normal()
                    score = int(rng.integers(-2, 3))
                    clock = float(rng.uniform(0, 1))
                    ball_half = int(rng.integers(0, 2))
                    controls = np.asarray([z, z*z, score, clock, clock*clock, ball_half], float)
                    # Randomized within series, with genuine overlap in every
                    # covariate region; nuisance outcomes are strongly nonzero.
                    x = int(rng.integers(0, 2))
                    residual = .55*residual + rng.normal(0, 65)
                    y = (700 + effect*x + 95*z - 30*z*z + 48*score
                         - 120*clock + 70*clock*clock + 55*ball_half
                         + cluster_error + residual)
                    rows.append(dict(x=x, y=float(y), controls=controls,
                        series_id=f"{split}-series-{cluster:03d}",
                        replay_id=f"{split}-replay-{cluster:03d}",
                        roster_id=f"roster-{cluster % 9}",
                        opponent_roster_id=f"opponent-{cluster % 11}",
                        region="Europe" if cluster % 2 else "North America",
                        event="synthetic-event", split=split,
                        season="rlcs-2024" if split == "train" else "rlcs-2025",
                        focal_team=event % 2, index=event, time=float(event*6),
                        stratum="regulation", score_diff=score,
                        remaining=300*clock, overtime=0,
                        initial_clearance=700., pretrend=0., earlier_width=700.))
            output.append(rows)
        return output

    def computed(result, label):
        required = ("effect", "ci95", "p", "n_series", "n_events")
        missing = [key for key in required if key not in result]
        if missing:
            raise AssertionError(f"{label}: missing result fields {missing}")
        numbers = [result["effect"], *result["ci95"], result["p"]]
        if any(value is None or not np.isfinite(value) for value in numbers):
            raise AssertionError(f"{label}: result was not computable: {result}")
        if not 0 <= result["p"] <= 1:
            raise AssertionError(f"{label}: invalid p-value")
        return {key: result[key] for key in required}

    nulls = {}
    for offset, idea in enumerate(("B02", "B10")):
        pvalues, effects = [], []
        for index in range(datasets):
            # All seeds are fixed in advance and independent across datasets.
            train, val = generate(100_000 + offset*10_000 + index, 0., idea)
            result = estimate(train, val, idea, seed=200_000 + offset*10_000 + index,
                              reps=reps, workers=1)
            value = computed(result, f"{idea} null dataset {index}")
            pvalues.append(float(value["p"]))
            effects.append(float(value["effect"]))
            if (index + 1) % 20 == 0:
                print(json.dumps({"acceptance": "null", "idea": idea,
                                  "completed": index + 1, "datasets": datasets}), flush=True)
        ks = kstest(pvalues, "uniform")
        pmean = float(np.mean(pvalues))
        rejection = float(np.mean(np.asarray(pvalues) < .05))
        passed = .35 <= pmean <= .65 and rejection <= .15 and ks.pvalue > .01
        nulls[idea] = dict(p_mean=pmean, rejection_at_005=rejection,
            ks_statistic=float(ks.statistic), ks_p=float(ks.pvalue),
            mean_effect=float(np.mean(effects)), datasets=datasets,
            replicates=reps, pvalues=pvalues, passed=bool(passed))
        if not passed:
            raise AssertionError(f"{idea}: null calibration failed: {nulls[idea]}")

    plants, invariance = {}, {}
    for offset, (idea, truth, threshold) in enumerate((("B02", 250., 150.), ("B10", 450., 200.))):
        train, val = generate(310_042 + offset, truth, idea)
        one = estimate(train, val, idea, seed=410_042 + offset, reps=399, workers=1)
        two = estimate(train, val, idea, seed=410_042 + offset, reps=399, workers=2)
        a, b = computed(one, f"{idea} plant 1 worker"), computed(two, f"{idea} plant 2 workers")
        # Do not compare timings/PIDs. Statistical output must be bit-identical,
        # not merely close, because replicate RNGs are indexed deterministically.
        invariant = a == b
        invariance[idea] = dict(workers=[1, 2], replicates=399,
                                bit_identical=bool(invariant), result=a)
        if not invariant:
            raise AssertionError(f"{idea}: worker-dependent inference: {a} != {b}")
        recovered = (a["effect"] >= threshold and a["ci95"][0] > 0
                     and a["p"] < .05 and abs(a["effect"]-truth) < max(50., .2*truth))
        plants[idea] = dict(truth=truth, result=a, recovered=bool(recovered))
        if not recovered:
            raise AssertionError(f"{idea}: planted effect not recovered: {plants[idea]}")

    permitted = ("rlcs-21-22", "rlcs-22-23", "rlcs-2024", "rlcs-2025")
    if tuple(namespace["ALLOWED_SEASONS"]) != permitted:
        raise AssertionError("Unexpected compact season allowlist")
    if tuple(namespace["TRAIN_SEASONS"]) != permitted[:3] or namespace["VAL_SEASON"] != permitted[-1]:
        raise AssertionError("Training/validation split boundary changed")
    rejected = []
    with tempfile.TemporaryDirectory(prefix="screen-v2-leakage-") as directory:
        base = Path(directory)
        forbidden = base / "rlcs-2026"
        forbidden.mkdir()
        alias = base / "apparently-allowed"
        alias.symlink_to(forbidden, target_is_directory=True)
        for path in (forbidden / "compact-0000.npz", base / "test" / "compact-0000.npz",
                     alias / "compact-0000.npz"):
            try:
                guard(path)
            except ValueError:
                rejected.append(str(path.relative_to(base)))
            else:
                raise AssertionError(f"Forbidden path passed pre-open guard: {path}")
        guard(base / "rlcs-2024" / "compact-0000.npz")
        guard(base / "rlcs-2025" / "compact-0000.npz")
    source = Path(inspect.getfile(estimate)).resolve()
    # Literal grep evidence is retained for review; path guards and allowlists
    # provide enforcement, whereas grep alone cannot prove dynamic I/O safety.
    sources = [source, source.with_name("screen.py"), source.with_name("events.py")]
    evidence = subprocess.run(["grep", "-nE", "ALLOWED_SEASONS|TRAIN_SEASONS|VAL_SEASON|NEVER read|guard_path|for season in", *map(str, sources)],
                              check=True, text=True, capture_output=True)
    result = dict(status="passed", null_checks=nulls, planted_checks=plants,
        worker_invariance=invariance,
        leakage_checks=dict(allowlist=list(permitted), rejected_paths=rejected,
                            grep_evidence=evidence.stdout),
        limits="Synthetic calibration covers the B02/B10 estimator, not all eighteen measurement designs.",
        elapsed_seconds=time.perf_counter()-started)
    print(json.dumps({"acceptance": "passed", "elapsed_seconds": result["elapsed_seconds"]}), flush=True)
    return result


# Effect thresholds alone are retained from screen_criterion. Sample-size,
# multi-season and final-confirmation replication gates do not define SCREEN.
THRESHOLDS={'B01':.15,'B02':150.,'B03':.02,'B04':.02,'B05':.07,'B06':.40,
            'B07':.05,'B08':.80,'B09':200.,'B10':200.,'B11':.08,'B12':.02,
            'B13':.08,'B14':.15,'B15':.03,'B16':.10,'B17':150.,'B18':.10}
UNITS={'B01':'gain (opposite uu/s per uu/s)','B02':'uu width','B03':'concession probability difference',
       'B04':'bits/action','B05':'exactly-one probability difference','B06':'Spearman rho',
       'B07':'slowing probability interaction','B08':'observed/independent pair-shortage ratio',
       'B09':'uu excursion (low minus high diversity)','B10':'uu clearance change',
       'B11':'response probability difference','B12':'concession probability difference',
       'B13':'lag-0.2s autocorrelation difference','B14':'rear/front response gain',
       'B15':'pulse probability modulation excess per 0.1s','B16':'seconds capped latency',
       'B17':'uu ball progress per doubling rarity','B18':'distinct-sector probability difference'}
ZH_UNITS={'B01':'每 1000 uu/秒创新对应的反向速度（uu/秒）','B02':'uu','B03':'个百分点','B04':'比特/动作','B05':'个百分点','B06':'相关系数','B07':'个百分点','B08':'倍','B09':'uu','B10':'uu','B11':'个百分点','B12':'个百分点','B13':'相关系数差','B14':'倍增益','B15':'个百分点/0.1秒','B16':'秒','B17':'uu/稀有度翻倍','B18':'个百分点'}
PROBABILITY_IDS={'B03','B05','B07','B11','B12','B15','B18'}
CHINESE={'B01':'横向补偿增益','B02':'前进历史相对后退历史的阵型宽度差','B03':'高脆弱性相对低脆弱性的失球概率差',
         'B04':'对手历史相对队友历史的预测损失差','B05':'恰好一人上前的超额概率','B06':'阵容旋转方向的分半相关',
         'B07':'宽间距下进攻者模糊性的额外减速概率','B08':'双人低 boost 风险相对独立基线的比值',
         'B09':'低响应多样性相对高多样性的额外回撤距离','B10':'追随防守带来的通道净宽变化',
         'B11':'停顿后的对手加速响应概率差','B12':'贯通通道相对封闭通道的失球概率差',
         'B13':'失球前阵型面积残差的额外持续性','B14':'后排横向响应的额外放大增益',
         'B15':'超出零模型的节拍调制概率','B16':'打破重复路线后的额外响应延迟',
         'B17':'队形稀有度每翻倍的推进距离变化','B18':'超出独立球员习惯基线的空间互补概率'}


def verdicts_v2(results,specs,smoke=False):
    qs=old.bh18({k:r['p'] for k,r in results.items()})
    for idea,result in results.items():
        result.update(id=idea,split='val',q=qs[idea],name=specs[idea]['name'],
                      screen_criterion=specs[idea]['screen_criterion'],
                      effect_threshold=THRESHOLDS[idea],effect_units=UNITS[idea],
                      bh_input_p=result['p'] if result['p'] is not None else 1.)
        result['effect_size']=dict(value=result['effect'],units=UNITS[idea],ci95=result['ci95'])
        if result['p'] is None or result['effect'] is None:
            result.update(status='not_computable',verdict='not_computable',screen_criterion_met=False,
                interpretation_zh=CHINESE[idea]+'：本次有效事件、对比或历史参考不足，无法估计（具体数据原因见 reason）。')
            continue
        effect=result['effect']; d=result['details']
        passed=effect<=THRESHOLDS[idea] if idea=='B08' else effect>=THRESHOLDS[idea]
        if idea=='B08':
            passed=passed and d.get('absolute_pair_shortage_difference',0)<=-.01
        if idea=='B14':
            passed=passed and d.get('observed_gain',-np.inf)>=1.20
        if idea=='B15':
            passed=passed and d.get('observed_modulation',0)>=.05
        result['screen_criterion_met']=bool(passed)
        result['verdict']='promising' if qs[idea]<.1 and passed else ('null' if result['p']>=.1 else 'weak')
        # Smoke cannot promote a scientific discovery; report intended rule separately.
        result['screen_rule_verdict']=result['verdict']
        if smoke and result['verdict']=='promising':
            result['verdict']='weak'
        result['effect_size']=dict(value=effect,units=UNITS[idea],ci95=result['ci95'])
        label={'promising':'值得扩大筛查，尚非确认','weak':'证据较弱','null':'未见清晰证据'}[result['verdict']]
        result['interpretation_zh']=f"{CHINESE[idea]}为 {effect*(100 if idea in PROBABILITY_IDS else 1000 if idea=='B01' else 1):.4g} {ZH_UNITS[idea]}，q={qs[idea]:.3g}；{label}。"


def select_smoke_v2(groups):
    ordered=sorted(groups,key=lambda g:(g[0]['_shard'],int(g[0]['start']),g[0]['replay_id']))
    selected=[]
    for season,count in ((TRAIN_SEASONS[0],1),(TRAIN_SEASONS[1],1),(TRAIN_SEASONS[2],3),(VAL_SEASON,5)):
        candidates=[g for g in ordered if g[0]['season']==season]
        seen=set()
        for g in candidates:
            if g[0]['series_id'] in seen:
                continue
            selected.append(g);seen.add(g[0]['series_id'])
            if len(seen)==count:
                break
    assert len(selected)<=10
    return selected


def _native_events_task(task):
    path,records,state_map=task
    lookup={str(r['replay_id']):r for r in records}
    goals,certificates=[],[]
    for rid,frames in events._native_replays(path,set(lookup)):
        gg,cert=events.build_replay_events(frames,lookup[rid],state_map)
        goals.extend(gg);certificates.append(cert)
    return goals,certificates


def event_tables_v2(groups,data_root,state_map_path,workers,artifacts):
    # Index only explicitly permitted seasons. Each native task reads selected
    # replay row groups, never a read-all-then-filter test-season fallback.
    selected=[g[0] for g in groups]
    records=events.native_index_for(selected,data_root)
    state_map=events.load_state_map(events.guard_path(state_map_path))
    by_path=defaultdict(list)
    for r in records:
        by_path[r['_frame_path']].append(r)
    tasks=[(path,records,state_map) for path,records in sorted(by_path.items())]
    goals,certs=[],[]
    def accept(result):
        gg,cc=result;goals.extend(gg);certs.extend(cc)
    if workers==1:
        for task in tasks:
            accept(_native_events_task(task))
    else:
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('fork')) as pool:
            for result in pool.map(_native_events_task,tasks,chunksize=1):
                accept(result)
    goals=sorted(goals,key=lambda r:(r['replay_id'],r['goal_number']))
    certs=sorted(certs,key=lambda r:r['replay_id'])
    pd.DataFrame(goals,columns=events.GOAL_COLUMNS).to_parquet(artifacts/'goal_events.parquet',index=False)
    pd.DataFrame(certs,columns=events.REPLAY_COLUMNS).to_parquet(artifacts/'replay_events.parquet',index=False)
    by_id=defaultdict(list)
    for g in goals:
        by_id[g['replay_id']].append(g)
    return by_id,{r['replay_id']:r for r in certs}


def _load_measurements(path):
    rows=[]
    with path.open('rb') as stream:
        while True:
            try:
                rows.extend(pickle.load(stream))
            except EOFError:
                break
    return rows


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=DEFAULT_INPUT)
    parser.add_argument('--output',type=Path,default=Path('.'))
    parser.add_argument('--scratch',type=Path)
    parser.add_argument('--data-root',type=Path,default=events.DEFAULT_DATA_ROOT)
    parser.add_argument('--state-map',type=Path,default=Path('state_map_rlcs.json'))
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--bootstrap-reps',type=int,default=2000)
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--self-test',action='store_true',help='Synthetic null, planted, worker-invariance and path guard gates; zero replay reads')
    parser.add_argument('--run',default='screen-v2-'+time.strftime('%Y%m%dT%H%M%S'))
    args=parser.parse_args(argv)
    if args.workers<1 or args.bootstrap_reps<2:
        parser.error('Positive workers and at least two replicates required')
    if args.self_test:
        report=run_acceptance()
        atomic_json(args.output/'results'/'screen_v2_acceptance.json',report)
        print(json.dumps(clean(report)),flush=True)
        return report
    if args.smoke and args.workers!=1:
        parser.error('Login-node real-data smoke is exactly one worker and at most 10 replays')
    if not args.smoke and not os.environ.get('SLURM_JOB_ID'):
        parser.error('Full screen requires a CPU allocation; NEVER run full replay work on login node')
    if not args.smoke and args.bootstrap_reps!=2000:
        parser.error('Full screen uses exactly 2000 prespecified replicates')
    if '/' in args.run or args.run in {'.','..'}:
        parser.error('run must be a single directory name')
    start=time.perf_counter()
    old._REPLICATE_TIMINGS.clear()
    artifacts=args.output/'artifacts'/args.run
    artifacts.mkdir(parents=True,exist_ok=False)
    def log(**values):
        print(json.dumps(clean(dict(elapsed_seconds=time.perf_counter()-start,**values))),flush=True)
    specs_path=Path(__file__).resolve().parents[2]/'status'/'ideas_brainstorm.json'
    specs={r['id']:r for r in json.loads(specs_path.read_text())}
    assert set(specs)==set(IDS)
    groups,audit=old.metadata_inventory(args.input)
    if args.smoke:
        groups=select_smoke_v2(groups)
    log(stage='metadata',replays=len(groups),val_series_inventory=audit['val_series'])
    t=time.perf_counter()
    goals,certs=event_tables_v2(groups,args.data_root,args.state_map,args.workers,artifacts)
    event_seconds=time.perf_counter()-t
    log(stage='native_events',validated=sum(bool(c['validated']) for c in certs.values()),goals=sum(map(len,goals.values())))
    thresholds={'policy':'Pre-registered SCREEN choices; no validation-target threshold selection',
                'B11_impulse_quantile':.95,'B03_B09_tertile_quantiles':[1/3,2/3],
                'ridge_alpha':10.,'max_train_fit_rows':50000,'reference_season':'rlcs-2024'}
    results,inference_seconds,counts={}, {}, {i:Counter() for i in IDS}
    exclusions,boost_audit=Counter(),[]
    extraction_start=time.perf_counter()
    completed=[]
    with tempfile.TemporaryDirectory(prefix='screen-v2-',dir=args.scratch) as temporary:
        temp=Path(temporary)
        streams={i:(temp/(i+'.pickle')).open('wb') for i in IDS}
        impulse_path=temp/'train-impulses.f32'
        with impulse_path.open('wb') as impulse_stream:
            def accept(item):
                completed.append(item['replay_id']);exclusions.update(item['exclusions'])
                if item['boost_audit']:
                    boost_audit.append(item['boost_audit'])
                np.asarray(item['train_impulses'],np.float32).tofile(impulse_stream)
                for idea,rows in item['rows'].items():
                    pickle.dump(rows,streams[idea],protocol=5)
                    counts[idea].update(r['split'] for r in rows)
                if args.smoke or len(completed)%50==0:
                    log(stage='measurements',replays_completed=len(completed))
            if args.smoke:
                for pair in groups:
                    rid=pair[0]['replay_id']
                    accept(process_replay_v2((pair,args.seed,None,goals[rid],certs[rid])))
            else:
                by_shard=defaultdict(list)
                for pair in groups:
                    assert len({r['_shard'] for r in pair})==1
                    by_shard[pair[0]['_shard']].append(pair)
                with ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('fork')) as pool:
                    for shard,pairs in sorted(by_shard.items()):
                        directory=old.unpack_shard(Path(shard),temp)
                        tasks=((pair,args.seed,directory,goals[pair[0]['replay_id']],certs[pair[0]['replay_id']]) for pair in pairs)
                        for item in pool.map(process_replay_v2,tasks,chunksize=1):
                            accept(item)
                        shutil.rmtree(directory)
        for stream in streams.values():
            stream.close()
        extraction_seconds=time.perf_counter()-extraction_start
        if impulse_path.stat().st_size:
            impulses=np.memmap(impulse_path,dtype=np.float32,mode='r')
            thresholds['B11_impulse_q95']=float(np.quantile(impulses,.95))
            thresholds['B11_train_increments']=int(len(impulses))
            del impulses
        if boost_audit:
            scale=max(r['max'] for r in boost_audit)
            saturated=sum(r['at_max'] for r in boost_audit if abs(r['max']-scale)<.001)
            total=sum(r['n'] for r in boost_audit)
            thresholds.update(boost_scale=scale if scale>0 and saturated/total>=.001 else None,
                              boost_saturation_fraction=saturated/total,
                              boost_training_min=min(r['min'] for r in boost_audit))
        log(stage='thresholds_frozen',thresholds=thresholds)
        for idea in IDS:
            t=time.perf_counter()
            rows=_load_measurements(temp/(idea+'.pickle'))
            train=[r for r in rows if r['split']=='train']
            val=[r for r in rows if r['split']=='val']
            del rows
            results[idea]=infer_v2(idea,train,val,thresholds,args.seed,args.bootstrap_reps,args.workers)
            inference_seconds[idea]=time.perf_counter()-t
            log(stage='inference',idea=idea,effect=results[idea]['effect'],p=results[idea]['p'],
                n_events=results[idea]['n_events'],n_series=results[idea]['n_series'],reason=results[idea].get('reason'))
            del train,val
    verdicts_v2(results,specs,args.smoke)
    verdict_counts=Counter(r['verdict'] for r in results.values())
    full_gate=verdict_counts['not_computable']<=3
    payload=dict(method='brainstorm_screen_v2',task='screen',split='val',is_baseline=False,updated=now(),
        metrics=dict(ideas=18,replays_processed=len(completed),
            n_train_replays=sum(g[0]['split']=='train' for g in groups),n_val_replays=sum(g[0]['split']=='val' for g in groups),
            primary_estimates=sum(r['p'] is not None for r in results.values()),elapsed_seconds=time.perf_counter()-start,
            **{v:verdict_counts[v] for v in ('promising','weak','null','not_computable')}),
        details=dict(ideas=results,smoke=args.smoke,production_ready=not args.smoke and full_gate,
            computability_gate=dict(maximum_not_computable=3,passed=full_gate,enforced=not args.smoke,
                smoke_exception='Ten replay execution test may lack rare event/roster support'),
            audit=audit,config=vars(args),processed_replay_ids=completed,measurement_counts=counts,
            native_event_audit=dict(replays=len(certs),validated=sum(bool(r['validated']) for r in certs.values()),
                verified_terminals=sum(bool(r['terminal_verified']) for r in certs.values()),
                failed_replay_reasons=dict(Counter(r['failure_reason'] for r in certs.values() if not r['validated']))),
            train_frozen=thresholds,exclusions=dict(exclusions),
            timing_seconds=dict(native_events=event_seconds,extraction=extraction_seconds,inference=inference_seconds),
            replicate_timings=list(old._REPLICATE_TIMINGS),
            source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (Path(__file__),Path(old.__file__),Path(events.__file__),specs_path)},
            input_manifest_sha256=old.input_identity(args.input),
            family=dict(size=18,adjustment='Benjamini-Hochberg',missing_primary_p=1.,promising_q_strictly_below=.1),
            limitations=['SCREEN of observed 2025 validation series, not an independent confirmation or causal result.',
                'All nuisance/reference fits are TRAIN-only; intervals condition on those frozen estimates.',
                'Partial series membership in compact is retained; series bootstrap includes all observed members, not a completeness claim.',
                'Sparse support and model/marginal-calibration diagnostics are reported, not replaced with exact-match feasibility gates.',
                'Cross-series shared-roster dependence can remain; B18 additionally reports shared-player/roster sensitivity.',
                'Smoke output exercises all 18 paths but is not a full-data scientific result.']))
    atomic_json(args.output/'results'/'screen_v2.json',payload)
    atomic_json(artifacts/'summary.json',payload)
    log(stage='complete',**dict(verdict_counts))
    if not args.smoke and not full_gate:
        raise RuntimeError('Production acceptance failed: >3 not_computable ideas; see concrete data reasons in screen_v2.json')
    return payload


if __name__=='__main__':
    main()
