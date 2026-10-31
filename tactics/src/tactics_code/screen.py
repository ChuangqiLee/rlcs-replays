"""Strict, development-only feasibility screen of the eighteen brainstorm ideas.

B01--B18 extract the specified observable quantities. infer_idea applies the
specified primary test only when its data/identification prerequisites exist.
Unavailable tests have p=None, enter the fixed BH family with p=1, and are never
called null. No relaxed surrogate is promoted to a primary result.

This module intentionally does not use iter_compact(root): that loader opens
test metadata before split filtering. Only explicitly allowlisted shard paths
are opened. --smoke reads slices for at most six unique replays, one worker.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import zipfile

import numpy as np
import pandas as pd

from .common import atomic_json, clean, now, split_for_season
from .data import parsed_json

TRAIN_SEASONS = ("rlcs-21-22", "rlcs-22-23", "rlcs-2024")
VAL_SEASON = "rlcs-2025"
ALLOWED_SEASONS = TRAIN_SEASONS + (VAL_SEASON,)
IDS = tuple(f"B{i:02d}" for i in range(1, 19))
MATCHED = {"B02", "B07", "B10", "B16"}
PRIMARY_ROWS = MATCHED | {"B01", "B04", "B05", "B06", "B08", "B14", "B15"}
DEFAULT_INPUT = Path("artifacts/p3-small-41104720-s42-w6-f10-ksweep/compact")
REQUIRED = {"ball", "players", "time", "frame", "live", "segment",
            "score_diff", "remaining", "overtime"}


def guard_path(path):
    """Reject 2026/test *before* any open, including symlinks into that split."""
    path = Path(path)
    if "2026" in str(path) or "2026" in str(path.resolve()):
        raise ValueError("NEVER read split 2026 (test)")
    if any(p == "test" for p in path.resolve().parts):
        raise ValueError("Test-split path forbidden")
    return path


def phase(replay_id, seed, length):
    # Same convention as tokens._phase; avoid its heavyweight sklearn import.
    digest = hashlib.sha256(f"{seed}:{replay_id}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % length


def explicit_region(meta):
    value = meta.get("region")
    if isinstance(value, str) and value.strip():
        return value
    path = parsed_json(meta.get("group_path"), [])
    for part in path:
        s = str(part).lower()
        for needle, region in (
            ("north-america", "North America"), ("south-america", "South America"),
            ("europe", "Europe"), ("oceania", "Oceania"),
            ("middle-east", "Middle East & North Africa"),
            ("asia-pacific", "Asia-Pacific"), ("sub-saharan", "Sub-Saharan Africa")):
            if needle in s.replace(" ", "-"):
                return region
        if "world-championship" in s or re.search(r"(?:^|-)major(?:-|$)", s) and "split" not in s:
            return "international"
    return None


def metadata_inventory(root):
    root = guard_path(root)
    extraction = json.loads(guard_path(root / "extraction.json").read_text())
    if extraction.get("state_map", {}).get("state_decoding") != "per_replay_decoded":
        raise ValueError("Extraction must use per-replay state decoding")
    records, headers, files = [], {}, []
    for season in ALLOWED_SEASONS:
        # Explicit season directory, never recursive root discovery.
        directory = guard_path(root / season)
        for path in sorted(directory.glob("compact-*.parquet")):
            guard_path(path)
            table = pd.read_parquet(path)
            shard = guard_path(path.with_suffix(".npz"))
            files.append(shard)
            with zipfile.ZipFile(shard) as archive:
                schema = {}
                for name in archive.namelist():
                    if not name.endswith(".npy"):
                        continue
                    with archive.open(name) as stream:
                        version = np.lib.format.read_magic(stream)
                        shape, order, dtype = (np.lib.format.read_array_header_1_0(stream) if version == (1, 0) else np.lib.format.read_array_header_2_0(stream))
                    schema[name[:-4]] = {"shape": list(shape), "fortran": order, "dtype": str(dtype)}
            if not REQUIRED <= schema.keys():
                raise ValueError(f"{shard}: missing {sorted(REQUIRED-schema.keys())}")
            headers[str(shard)] = schema
            for row in table.to_dict("records"):
                if row.get("season") != season or row.get("split") != split_for_season(season):
                    raise ValueError("Season/split mismatch; no array data opened")
                if row["split"] not in {"train", "val"}:
                    raise ValueError("NEVER read split 2026 (test)")
                diag = parsed_json(row.get("state_decoding_details"), {})
                if row.get("state_decoding") != "per_replay_decoded" or diag.get("failures", [True]):
                    raise ValueError(f"Unverified state decode: {row.get('replay_id')}")
                if float(row["fps"]) != 10:
                    raise ValueError("This screen requires the specified 10 Hz compact")
                row["_shard"] = str(shard)
                row["region"] = explicit_region(row)
                # Whole path is an explicitly weaker event control; no invented event parser.
                row["event"] = row.get("group_path")
                records.append(row)
    if not records:
        raise ValueError("No development metadata found")
    by_replay = defaultdict(list)
    for row in records:
        by_replay[row["replay_id"]].append(row)
    for rid, pair in by_replay.items():
        if len(pair) != 2 or {int(r["focal_team"]) for r in pair} != {0, 1}:
            raise ValueError(f"Duplicate or missing perspective: {rid}")
        if len({(r["series_id"], r["season"], r["split"]) for r in pair}) != 1:
            raise ValueError(f"Inconsistent replay grouping: {rid}")
        if not all(isinstance(r.get("series_id"), str) and r["series_id"] for r in pair):
            raise ValueError("Known series IDs required")
    series_splits = defaultdict(set)
    for row in records:
        series_splits[row["series_id"]].add(row["split"])
    if any(len(v) != 1 for v in series_splits.values()):
        raise ValueError("Series crosses development split")
    train = [r for r in records if r["split"] == "train"]
    val = [r for r in records if r["split"] == "val"]
    seen = {r[k] for r in train for k in ("roster_id", "opponent_roster_id") if r.get(k)}
    supported = [r for r in val if r.get("roster_id") in seen and r.get("opponent_roster_id") in seen]
    roster_series = defaultdict(set)
    for row in val:
        roster_series[row["roster_id"]].add(row["series_id"])
    audit = {
        "development_replays": len(by_replay),
        "train_replays": len({r["replay_id"] for r in train}),
        "val_replays": len({r["replay_id"] for r in val}),
        "val_series": len({r["series_id"] for r in val}),
        "val_roster_effect_support_rows": len(supported),
        "val_rosters_with_eight_series": sum(len(s) >= 8 for s in roster_series.values()),
        "max_val_series_per_roster": max(map(len, roster_series.values()), default=0),
        "region_coverage_val": sum(r["region"] is not None for r in val) / max(1, len(val)),
        "terminal_score_certified": all(r.get("terminal_score_verified") is True for r in records),
        "terminal_reason": "Inspected compact metadata has state decoding, but no native final-frame/last-goal/header-score certification",
        "terminal_certification_rows": sum(r.get("terminal_score_verified") is True for r in records),
        "complete_series_certified": all(r.get("series_membership_complete") is True for r in records),
        "series_reason": "Compact lists included members; no independent complete membership census",
        "metadata_fields": sorted(set.intersection(*(set(r) for r in records))),
        "read_seasons": list(ALLOWED_SEASONS),
        "test_opened": False,
        "schema": headers,
        "extraction_options": extraction.get("options"),
        "extraction_state_map": extraction.get("state_map"),
    }
    return list(by_replay.values()), audit


def read_slice(meta):
    """Read only this replay's C-order NPY slices; smoke never loads a whole shard."""
    start, stop = int(meta["start"]), int(meta["stop"])
    arrays = {}
    with zipfile.ZipFile(guard_path(meta["_shard"])) as archive:
        for key in REQUIRED:
            with archive.open(key + ".npy") as stream:
                version = np.lib.format.read_magic(stream)
                shape, fortran, dtype = (np.lib.format.read_array_header_1_0(stream) if version == (1, 0) else np.lib.format.read_array_header_2_0(stream))
                if fortran or dtype.hasobject:
                    raise ValueError(f"{key}: unsupported memory layout")
                width = math.prod(shape[1:])
                header = stream.tell()
                stream.seek(header + start * width * dtype.itemsize)
                raw = stream.read((stop-start) * width * dtype.itemsize)
                arrays[key] = np.frombuffer(raw, dtype=dtype).reshape((stop-start,) + shape[1:])
    return arrays


def unpack_shard(shard, destination):
    """Full batch only: decompress required arrays once, workers mmap by replay."""
    directory = destination / hashlib.sha256(str(shard).encode()).hexdigest()[:16]
    directory.mkdir()
    with zipfile.ZipFile(guard_path(shard)) as archive:
        for key in REQUIRED:
            with archive.open(key + ".npy") as source, (directory / (key + ".npy")).open("wb") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
    return str(directory)


class Context:
    def __init__(self, meta, arrays, seed):
        self.m, self.a, self.seed = meta, arrays, seed
        self.t, self.fps = arrays["time"], float(meta["fps"])
        p, b = arrays["players"], arrays["ball"]
        n = len(self.t)
        delta = b[:, None, :2] - p[:, :, :2]
        self.dist = np.linalg.norm(delta, axis=2)
        self.toward = np.divide(np.sum(p[:, :, 3:5]*delta, axis=2), self.dist,
                                out=np.full((n, 6), np.nan), where=self.dist > 0)
        self.smooth_velocity = np.full((n, 6, 3), np.nan)
        self.segment_age = np.zeros(n)
        self.ot_age = np.zeros(n)
        valid = (np.isfinite(p[:, :, :7]).all(axis=(1, 2)) &
                 np.isfinite(b[:, :6]).all(axis=1) & np.isfinite(self.t) &
                 arrays["live"].astype(bool) & (arrays["segment"] >= 0) &
                 np.isfinite(arrays["score_diff"]) & np.isfinite(arrays["remaining"]) &
                 np.isfinite(arrays["overtime"]))
        if n > 1:
            dt = np.diff(self.t)
            continuity = (dt > 0) & (dt <= .16) & (np.diff(arrays["segment"]) == 0)
            jump = ((np.linalg.norm(np.diff(p[:, :, :3], axis=0), axis=2).max(axis=1) > 500) |
                    (np.linalg.norm(np.diff(b[:, :3], axis=0), axis=1) > 1200))
            valid[1:] &= ~jump
            # Exact unmoving coordinates >=1 s are conservatively unmeasurable:
            # never infer valid defence from a stale/missing player track.
            equal = (np.diff(p[:, :, :3], axis=0) == 0).all(axis=2)
            run = np.zeros(6, dtype=int)
            for i in range(1, n):
                run = np.where(equal[i-1] & continuity[i-1], run+1, 0)
                if (run >= 10).any():
                    valid[max(0, i-10):i+1] = False
        seg_start, ot_start = 0, None
        for i in range(n):
            if i == 0 or arrays["segment"][i] != arrays["segment"][i-1] or not arrays["live"][i-1]:
                seg_start = i
            self.segment_age[i] = self.t[i]-self.t[seg_start]
            if arrays["overtime"][i] == 1:
                if ot_start is None:
                    ot_start = i
                self.ot_age[i] = self.t[i] - self.t[ot_start]
            elif arrays["live"][i]:
                ot_start = None
            j = max(seg_start, i-3)
            self.smooth_velocity[i] = np.mean(p[j:i+1, :, 3:6], axis=0)
        self.valid = valid
        self.bad_prefix = np.r_[0, np.cumsum(~valid)]

    def idx(self, i, seconds):
        return i + int(round(seconds*self.fps))

    def ok(self, i, past, future):
        lo, hi = self.idx(i, -past), self.idx(i, future)
        if lo < 0 or hi >= len(self.t) or self.segment_age[lo] < 2 - 1e-6:
            return False
        if self.bad_prefix[hi+1] != self.bad_prefix[lo]:
            return False
        segment = self.a["segment"][lo:hi+1]
        dt = np.diff(self.t[lo:hi+1])
        return bool(np.all(segment == segment[0]) and np.all((dt > 0) & (dt <= .16))
                    and abs((self.t[hi]-self.t[lo])-(past+future)) <= .16)

    def anchors(self, past, future, spacing=6):
        step = int(round(spacing*self.fps))
        for i in range(phase(self.m["replay_id"], self.seed, step), len(self.t), step):
            if self.ok(i, past, future):
                yield i

    def row(self, i, **values):
        b, p = self.a["ball"][i], self.a["players"][i, :, :7]
        previous = self.a["ball"][self.idx(i, -1):i+1, :6]
        score, remaining, overtime = (float(self.a[k][i]) for k in ("score_diff", "remaining", "overtime"))
        row = {k:self.m.get(k) for k in ("replay_id", "focal_team", "series_id", "season",
                                        "split", "roster_id", "opponent_roster_id", "region", "event")}
        row.update(index=i, time=float(self.t[i]), score_diff=score, remaining=remaining,
                   overtime=overtime, ot_duration=float(self.ot_age[i]),
                   segment_age=float(self.segment_age[i]),
                   stratum="overtime" if overtime else "zero_live" if remaining == 0 else "regulation",
                   ball=b.astype(float).tolist(), players=p.astype(float).tolist(),
                   past_ball=previous.astype(float).tolist(),
                   past_players=self.a["players"][self.idx(i, -1):i+1, :, :7].astype(float).tolist())
        row.update(values)
        return row


def matching_controls(row, idea):
    """Fixed physical scales, never fit on validation; leave exposure identifiable."""
    b = np.asarray(row["ball"], float)
    p = np.asarray(row["players"], float)
    past = np.asarray(row["past_ball"], float)
    bs = np.array([4096, 5120, 2044, 2300, 2300, 2300])
    ps = np.array([4096, 5120, 2044, 2300, 2300, 2300, 255])
    controls = [row["score_diff"], row["remaining"]/300, (row["remaining"]/300)**2,
                row["ot_duration"]/300, min(row["segment_age"], 120)/120]
    controls.extend(b / bs)
    # Ball path, including height; history is observational context, except B02
    # whose longitudinal history is the exposure itself.
    if idea == "B02":
        controls.extend(p[:3, :3].mean(axis=0) / ps[:3])
        controls.extend(p[:3, 3:7].mean(axis=0) / ps[3:7])
        controls.extend((p[3:] / ps).ravel())
        controls.extend(past[:, [0, 2]].mean(axis=0) / bs[[0, 2]])
    elif idea == "B07":
        controls.extend([row["min_tau"]/5, row["mean_distance"]/2500,
                         row["mean_speed"]/2300])
        controls.extend((p[3:] / ps).ravel())
        controls.extend(p[:3, [2, 6]].mean(axis=0) / ps[[2, 6]])
        controls.extend((past / bs).mean(axis=0))
    else:
        controls.extend((p / ps).ravel())
        controls.extend((past / bs).ravel())
        if idea == "B10":
            controls.extend([row["initial_clearance"]/2000,
                             row.get("pretrend", row.get("pre_change", 0))/2000])
        elif idea == "B16":
            controls.extend([row["actual_turn_delta_x"]/1000])
            controls.extend((np.asarray(row["past_players"]) / ps).ravel())
    return np.asarray(controls, float)


def model_controls(row, idea):
    """Context C in fixed physical units; identities are handled by exact blocks/models."""
    b, p = np.asarray(row["ball"]), np.asarray(row["players"])
    bs = np.array([4096,5120,2044,2300,2300,2300])
    ps = np.array([4096,5120,2044,2300,2300,2300,255])
    base = [row["score_diff"], row["remaining"]/300, (row["remaining"]/300)**2,
            row["overtime"], row["ot_duration"]/300, row["segment_age"]/120]
    base.extend(b/bs)
    if idea == "B06":
        base.extend(p[:3].mean(axis=0)/ps)
        base.extend([row["width"]/8192, row["depth"]/10240,
                     row["ball_circulation"], row["left_occupancy"]])
        base.extend((p[3:]/ps).ravel())
    else:
        base.extend((p/ps).ravel())
    base.extend((np.asarray(row["past_ball"])/bs).ravel())
    if idea == "B14":
        base.extend(np.asarray(row["reversal_path"])/2300)
        base.extend(np.asarray(row["starting_vx"])/2300)
        base.extend(np.asarray(row["y_spacing"])/5120)
    return np.asarray(base, float)


def process_replay(task):
    pair, seed, mmap_dir = task
    output = {idea: {"rows": [], "n_events": 0, "sum_x": 0., "nx": 0,
                     "sum_y": 0., "ny": 0, "series": [], "samples": []} for idea in IDS}
    boosts = []
    for meta in pair:
        if meta["season"] not in ALLOWED_SEASONS or meta["split"] not in {"train", "val"}:
            raise ValueError("NEVER read split 2026 (test)")
        if mmap_dir:
            start, stop = int(meta["start"]), int(meta["stop"])
            arrays = {key: np.load(Path(mmap_dir)/(key+".npy"), mmap_mode="r", allow_pickle=False)[start:stop]
                      for key in REQUIRED}
        else:
            arrays = read_slice(meta)
        context = Context(meta, arrays, seed)
        if meta["split"] == "train":
            raw = arrays["players"][:, :, 6]
            raw = raw[np.isfinite(raw)]
            if len(raw):
                maximum = float(raw.max())
                boosts.append({"min":float(raw.min()), "max":maximum, "n":len(raw),
                               "at_max":int(np.sum(np.isclose(raw, maximum, atol=.001)))})
        for idea in IDS:
            rows = globals()[idea](context)
            dest = output[idea]
            if meta["split"] == "val":
                dest["n_events"] += len(rows)
                if rows:
                    dest["series"].append(meta["series_id"])
                for row in rows:
                    for key in ("x", "y"):
                        value = row.get(key)
                        if isinstance(value, (int, float, np.number)) and np.isfinite(value):
                            dest["sum_"+key] += float(value)
                            dest["n"+key] += 1
                # Small diagnostic values only; do not retain huge history blocks
                # for an unidentifiable primary fit.
                if rows and len(dest["samples"]) < 2:
                    r = rows[0]
                    dest["samples"].append({k:r[k] for k in ("x", "y", "pretrend", "frozen_change", "ball_impulse") if k in r})
            if idea in PRIMARY_ROWS:
                for row in rows:
                    row["controls"] = (matching_controls(row, idea) if idea in MATCHED
                                       else model_controls(row, idea))
                    for key, value in tuple(row.items()):
                        if isinstance(value, list):
                            try:
                                array = np.asarray(value)
                            except ValueError:
                                continue
                            if array.dtype.kind in "bifu" and array.size > 6:
                                row[key] = array.astype(np.float32)
                dest["rows"].extend(rows)
    return {"ideas": output, "boosts": boosts, "replay_id":pair[0]["replay_id"]}

# Raw B01--B08 measurements; fitting and inference are performed downstream.

def _early_at(c, i, seconds):
    """Index a compact timestamp through the checked context contract."""
    return c.idx(i, seconds)


def _early_history(c, i, past=1.0):
    lo = _early_at(c, i, -past)
    # Fixed sampled blocks preserve receiver covariance and temporal ordering.
    return (c.a["ball"][lo:i + 1, :6].astype(float),
            c.a["players"][lo:i + 1, :, :7].astype(float))


def B01(c):
    """Compensation gain inputs; matched receiver-block null, series randomization."""
    rows = []
    for i in c.anchors(1.0, .7):
        order = np.argsort(c.dist[i, :3])
        if c.dist[i, order[1]] - c.dist[i, order[0]] < 100:
            continue
        focal = int(order[0])
        receivers = [j for j in range(3) if j != focal]
        j, k = _early_at(c, i, .2), _early_at(c, i, .7)
        v = c.smooth_velocity
        u = float(v[j, focal, 0] - v[i, focal, 0])
        response = float(np.sum(v[k, receivers, 0] - v[j, receivers, 0]))
        ball_history, player_history = _early_history(c, i)
        rows.append(c.row(i, x=u, y=response, source_player=focal,
                          ball_history=ball_history.tolist(),
                          player_history=player_history.tolist(),
                          receiver_block=v[j:k + 1, receivers, :].tolist(),
                          source_block=v[i:j + 1, focal, :].tolist(),
                          realized_ball=c.a["ball"][i:k + 1, :6].tolist()))
    return rows


def B02(c):
    """Forward-minus-backward width; matched history contrast, series bootstrap."""
    rows = []
    for i in c.anchors(2.0, .5):
        ball = c.a["ball"]
        if abs(float(ball[i, 4])) >= 300:
            continue
        displacement = float(ball[i, 1] - ball[_early_at(c, i, -1.5), 1])
        stop = _early_at(c, i, .5)
        width = np.ptp(c.a["players"][i:stop + 1, :3, 0], axis=1)
        p = c.a["players"][i, :3, :7]
        earlier = _early_at(c, i, -1.5)
        sensitivities = {str(h): float(ball[i, 1] - ball[_early_at(c, i, -h), 1])
                         for h in (1.0, 2.0)}
        rows.append(c.row(i, x=1 if displacement > 600 else -1 if displacement < -600 else 0, y=float(width.mean()),
                          displacement=displacement, history_displacements=sensitivities,
                          earlier_width=float(np.ptp(c.a["players"][earlier, :3, 0])),
                          centroid=p[:, :3].mean(axis=0).tolist(),
                          mean_velocity=p[:, 3:6].mean(axis=0).tolist(),
                          mean_boost=float(p[:, 6].mean()),
                          baseline_control_exception="exclude current width and individual current x"))
    return rows


def _early_coverage(players, nx=33, ny=21):
    xx, yy = np.meshgrid(np.linspace(-4096., 4096., nx), np.linspace(-5120., 0., ny))
    grid = np.column_stack((xx.ravel(), yy.ravel()))
    distance = np.linalg.norm(grid[:, None, :] - players[None, :, :2], axis=2)
    own = distance[:, :3]
    rival = distance[:, 3:].min(axis=1)
    nearest = own.min(axis=1)
    # The specification declares nearest-distance gaps <100 uu uncertain.
    reliable = np.abs(nearest - rival) >= 100.
    owned = nearest < rival
    A = float(owned.mean())
    deleted = [float((np.delete(own, j, axis=1).min(axis=1) < rival).mean())
               for j in range(3)]
    losses = A - np.asarray(deleted)
    return dict(A=A, B=float(losses.max() / A) if A >= .10 else None,
                omitted=int(np.argmax(losses)), uncertain_fraction=float((~reliable).mean()),
                # Keep literal nearest-cell A/B plus uncertainty-aware sensitivity.
                A_certain=float((owned & reliable).mean()),
                deletion_coverage=deleted)


def B03(c):
    """Virtual-deletion brittleness; audited goal risk required for series test."""
    rows = []
    for i in c.anchors(1.0, 0.):
        p = c.a["players"][i]
        coverage = _early_coverage(p)
        if coverage["B"] is None:
            continue
        coarse = _early_coverage(p, 17, 11)
        rows.append(c.row(i, x=coverage["B"], y=None, **coverage,
                          coarse_grid=coarse,
                          nearest_defender=float(c.dist[i, :3].min()),
                          goal_side=int(np.sum(p[:3, 1] < c.a["ball"][i, 1])),
                          outcome_unavailable="compact lacks verified final-native-frame/last-goal audit"))
    return rows


def B04(c):
    """L/S/R prediction features; matched history shuffles, paired series loss."""
    rows = []
    for i in c.anchors(1.0, .5):
        stop = _early_at(c, i, .5)
        ball_history, histories = _early_history(c, i)
        players = c.a["players"][i, :, :7]
        for focal in range(3):
            teammates = [j for j in range(3) if j != focal]
            opp_distance = np.linalg.norm(players[3:, :2] - players[focal, :2], axis=1)
            opponents = (3 + np.argsort(opp_distance, kind="stable")[:2]).tolist()
            dx = float(c.a["players"][stop, focal, 0] - players[focal, 0])
            label = 0 if dx < -150 else 2 if dx > 150 else 1
            base = np.concatenate((players.ravel(), histories[:, focal, :].ravel(),
                                   ball_history.ravel()))
            own_features = histories[:, teammates, :].ravel()
            opp_features = histories[:, opponents, :].ravel()
            assert own_features.shape == opp_features.shape
            rows.append(c.row(i, x=focal, y=label, displacement=dx,
                              base_features=base.tolist(),
                              teammate_features=own_features.tolist(),
                              opponent_features=opp_features.tolist(),
                              teammate_slots=teammates, opponent_slots=opponents,
                              teammate_distances=np.linalg.norm(players[teammates, :2] - players[focal, :2], axis=1).tolist(),
                              opponent_distances=opp_distance[np.argsort(opp_distance, kind="stable")[:2]].tolist(),
                              teammate_speeds=np.linalg.norm(players[teammates, 3:5], axis=1).tolist(),
                              opponent_speeds=np.linalg.norm(players[opponents, 3:5], axis=1).tolist()))
    return rows


def B05(c):
    """Exactly-one approach; calibrated marginals and complete pseudo-pair null."""
    rows = []
    for i in c.anchors(1.0, .5):
        nearest = np.argsort(c.dist[i, :3])[:2]
        distance = c.dist[i, nearest]
        if distance.max() > 1500 or abs(float(distance[0] - distance[1])) > 200:
            continue
        if c.a["ball"][i, 2] >= 400 or c.dist[i, 3:].min() > 2000:
            continue
        stop = _early_at(c, i, .5)
        reduction = distance - c.dist[stop, nearest]
        dt = np.diff(c.t[i:stop + 1])
        closing = -np.diff(c.dist[i:stop + 1, nearest], axis=0) / dt[:, None]
        approach = (reduction >= 150) & (closing.mean(axis=0) > 0)
        ids = c.m.get("player_ids")
        if isinstance(ids, str):
            try:
                ids = json.loads(ids)
            except (ValueError, TypeError):
                ids = None
        ball_history, player_history = _early_history(c, i)
        rows.append(c.row(i, x=1, y=approach.astype(int).tolist(),
                          exactly_one=int(approach.sum() == 1), slots=nearest.tolist(),
                          selected_player_ids=[ids[j] for j in nearest] if isinstance(ids, (list, tuple)) and len(ids) >= 3 else None,
                          distance_gap=float(abs(distance[0] - distance[1])),
                          initial_distances=distance.tolist(), reduction=reduction.tolist(),
                          mean_closing=closing.mean(axis=0).tolist(),
                          ball_history=ball_history.tolist(), player_history=player_history.tolist(),
                          response_block=c.a["players"][i:stop + 1, nearest, :7].tolist(),
                          realized_ball=c.a["ball"][i:stop + 1, :6].tolist()))
    return rows


def B06(c):
    """Signed planar circulation; roster split halves and restricted label null."""
    rows = []
    for i in c.anchors(1.0, 0.):
        p = c.a["players"][i, :3, :7]
        r = p[:, :2] - p[:, :2].mean(axis=0)
        w = p[:, 3:5] - p[:, 3:5].mean(axis=0)
        denominator = float(np.sum(r * r))
        if denominator / 3 < 300 ** 2:
            continue
        L = float(np.sum(r[:, 0] * w[:, 1] - r[:, 1] * w[:, 0]) / denominator)
        b = c.a["ball"][i]
        br = b[:2] - p[:, :2].mean(axis=0)
        bv = b[3:5] - p[:, 3:5].mean(axis=0)
        ball_circulation = float((br[0] * bv[1] - br[1] * bv[0]) / max(float(np.dot(br, br)), 1.))
        rows.append(c.row(i, x=1, y=L, L=L, rms_radius=float(np.sqrt(denominator / 3)),
                          centroid=p[:, :2].mean(axis=0).tolist(),
                          width=float(np.ptp(p[:, 0])), depth=float(np.ptp(p[:, 1])),
                          ball_circulation=ball_circulation,
                          left_occupancy=float(np.mean(p[:, 0] < 0)),
                          baseline_control_exception="exclude focal roster/player identities and full instantaneous state"))
    return rows


def B07(c):
    """Ambiguity-by-separation slowing interaction; standardized series bootstrap."""
    rows = []
    for i in c.anchors(1.0, .5):
        b, p = c.a["ball"][i], c.a["players"][i]
        if b[2] >= 300 or abs(float(b[5])) >= 300:
            continue
        eligible = [j for j in range(3) if c.toward[i, j] > 300 and 500 <= c.dist[i, j] <= 2500]
        if len(eligible) < 2:
            continue
        tau = {j: float(c.dist[i, j] / c.toward[i, j]) for j in eligible}
        first, second = sorted(eligible, key=lambda j: (tau[j], j))[:2]
        gap = abs(tau[first] - tau[second])
        if .15 < gap < .5:
            continue
        separation = abs(float(p[first, 0] - p[second, 0]))
        if 600 < separation < 1200:
            continue
        defender = 3 + int(np.argmin(c.dist[i, 3:]))
        if c.toward[i, defender] < 500 or c.dist[i, defender] <= 800:
            continue
        stop = _early_at(c, i, .5)
        slowing = float(c.toward[i, defender] - c.toward[stop, defender])
        ambiguous, wide = int(gap <= .15), int(separation >= 1200)
        rows.append(c.row(i, x=2 * wide + ambiguous, y=int(slowing >= 300),
                          ambiguous=ambiguous, wide=wide, slots=[first, second], defender=defender,
                          tau_gap=gap, min_tau=min(tau[first], tau[second]),
                          separation=separation, slowing=slowing,
                          mean_distance=float(c.dist[i, [first, second]].mean()),
                          mean_speed=float(np.linalg.norm(p[[first, second], 3:5], axis=1).mean()),
                          realized_ball_acceleration=((c.a["ball"][stop, 3:6] - b[3:6]) / (c.t[stop] - c.t[i])).tolist(),
                          baseline_control_exception="broad urgency controls; exclude exact candidate states"))
    return rows


def B08(c):
    """Future raw shortages; train-frozen boost scale, log pair-ratio bootstrap."""
    rows = []
    for i in c.anchors(1.0, 1.0):
        stop = _early_at(c, i, 1.0)
        ball_history, player_history = _early_history(c, i)
        raw = c.a["players"][stop, :3, 6]
        if not np.isfinite(raw).all():
            continue
        rows.append(c.row(i, x=1, y=raw.astype(float).tolist(),
                          future_boost=raw.astype(float).tolist(),
                          initial_state=c.a["players"][i, :, :7].tolist(),
                          ball_history=ball_history.tolist(),
                          boost_history=player_history[:, :, 6].tolist(),
                          null="sum of three own-team p_i*p_j, no future-total control"))
    return rows

# Raw feature extractors only. Nuisance fitting and inference belong to main screen.

def _late_velocity(c):
    """Only past .3 seconds; reset smoothing at every live segment boundary."""
    raw = np.asarray(c.a['players'][:, :, 3:6], float)
    out = np.full_like(raw, np.nan)
    k = max(1, int(round(.3*c.fps)))
    for i in range(k, len(raw)):
        if c.a['segment'][i] >= 0 and np.all(c.a['segment'][i-k:i+1] == c.a['segment'][i]):
            out[i] = np.mean(raw[i-k:i+1], axis=0)
    return out


def _late_clearance(defenders, start, end):
    d = end-start
    dd = float(d@d)
    w = np.zeros(len(defenders)) if dd == 0 else np.clip((defenders-start)@d/dd, 0, 1)
    return float(np.clip(np.min(np.linalg.norm(defenders-(start+w[:, None]*d), axis=1)), 0, 2000))


def _late_reversals(c):
    """Forward-to-backward vy, both sides sustained .3 s; episodes >=3 s apart."""
    b = c.a['ball'][:, 4]
    k = max(1, int(round(.3*c.fps)))
    last, armed, previous_segment = -np.inf, False, None
    for i in range(k+1, len(b)-k):
        segment = c.a['segment'][i]
        if segment < 0 or segment != previous_segment:
            armed = False
        previous_segment = segment
        if not c.ok(i, .4, .3):
            armed = False
            continue
        if np.all(b[i-k:i+1] > 500):
            armed = True
        if armed and np.all(b[i:i+k+1] < -500):
            armed = False
            if c.t[i]-last >= 3:
                last = c.t[i]
                yield i


def B09(c):
    """Train-residualized reversal diversity versus goal-absorbed excursion.
    Null: no diversity association beyond average response; whole-series bootstrap.
    The reported complete-horizon excursion is diagnostic, not the primary endpoint.
    """
    rows = []
    v = _late_velocity(c)
    for i in _late_reversals(c):
        if not c.ok(i, .4, 2.5):
            continue
        j, a, b = c.idx(i, .4), c.idx(i, .5), c.idx(i, 2.5)
        dv = v[j, :3, 1]-v[i, :3, 1]
        excursion = max(0., float(c.a['ball'][a, 1]-np.min(c.a['ball'][a:b+1, 1])))
        rear = int(np.argmin(c.a['players'][i, :3, 1]))
        rows.append(c.row(i, x=float(np.std(dv)), y=None,
            diversity=float(np.std(dv)), mean_delta_vy=float(np.mean(dv)),
            initial_vy=v[i, :3, 1].tolist(), rear_delta_vy=float(dv[rear]),
            reversal_magnitude=float(c.a['ball'][c.idx(i, -.3), 4]-c.a['ball'][j, 4]),
            complete_horizon_excursion=excursion,
            primary_unavailable='Complete terminal-goal audit required for absorbed horizon.'))
    return rows


def B10(c):
    """Pursuit/no-pursuit clearance-change contrast; matched series-bootstrap test.
    Match initial clearance and previous .5 s opening. Freeze teammate at onset.
    """
    rows = []
    p, ball = c.a['players'][:, :, :2], c.a['ball'][:, :2]
    for i in c.anchors(1., 1.):
        half, end, pre = c.idx(i, .5), c.idx(i, 1.), c.idx(i, -.5)
        for source in range(3):
            if c.dist[i, source] <= 700 or c.dist[half, source]-c.dist[i, source] < 300:
                continue
            initial = np.linalg.norm(p[i, 3:]-p[i, source], axis=1)
            after = np.linalg.norm(p[half, 3:]-p[half, source], axis=1)
            pursue = (initial <= 1500) & (initial-after >= 200) & (c.dist[half, 3:]-c.dist[i, 3:] >= 200)
            teammate = min([j for j in range(3) if j != source], key=lambda j: c.dist[i, j])
            old = _late_clearance(p[i, 3:], p[i, teammate], ball[i])
            new = _late_clearance(p[end, 3:], p[end, teammate], ball[end])
            before = _late_clearance(p[pre, 3:], p[pre, teammate], ball[pre])
            frozen = _late_clearance(p[end, 3:], p[i, teammate], ball[i])-old
            rows.append(c.row(i, x=int(np.any(pursue)), y=new-old,
                source_player=source, frozen_teammate=teammate, initial_clearance=old,
                match_unit=str(parsed_json(c.m.get("player_ids"), [None]*6)[source]),
                pretrend=old-before, frozen_lane_change=frozen, frozen_lane=frozen,
                departing_distance_change=float(c.dist[half, source]-c.dist[i, source]),
                pursuit_count=int(np.sum(pursue))))
    return rows


def B11(c):
    """Pause versus uninterrupted geometric response; retain undefined impulse cutoff.
    Exact primary needs declared 'large ball impulse' threshold, same-elapsed-time
    matched episodes, reverse-lag diagnostic, and whole-series centered bootstrap.
    """
    rows = []
    n, k = len(c.t), max(1, int(round(.3*c.fps)))
    half = max(1, int(round(.5*c.fps)))
    for source in range(3):
        qualified, start, run, prior_segment = None, None, 0, None
        used = set()
        for i in range(n):
            seg = c.a['segment'][i]
            if seg < 0 or seg != prior_segment:
                qualified, start, run = None, None, 0
            prior_segment = seg
            if not c.ok(i, .5, .8):
                qualified, start, run = None, None, 0
                continue
            approach = 700 <= c.dist[i, source] <= 1500 and c.toward[i, source] >= 500
            if qualified is None:
                run = run+1 if approach else 0
                if run >= k+1 and int(np.argmin(c.dist[i-k, :3])) == source:
                    start, qualified = i-k, i
                continue
            if c.dist[i, source] <= 400:
                qualified, start, run = None, None, 0
                continue
            end = i+k
            pause = np.all(c.toward[i:end+1, source] < 100) and np.all(c.dist[i:end+1, source] > 400)
            uninterrupted = np.all(c.toward[i:end+1, source] >= 500)
            if not (pause or uninterrupted) or np.any(c.dist[i:end+1] <= 300):
                continue
            elapsed_bin = int(np.floor((c.t[i]-c.t[qualified])/.3+1e-6))
            key = (start, elapsed_bin, bool(pause))
            if key in used:
                continue
            used.add(key)
            opp = 3+int(np.argmin(c.dist[i, 3:]))
            response = float(c.toward[end+half, opp]-c.toward[end, opp] >= 400)
            reverse = float(c.toward[i, opp]-c.toward[i-half, opp] >= 400)
            impulse = np.linalg.norm(np.diff(c.a['ball'][i:end+1, 3:6], axis=0), axis=1)
            rows.append(c.row(end, x=int(pause), y=None,
                diagnostic_response=response, episode=f'{source}:{start}',
                source_player=source, frozen_opponent=opp, onset_time=float(c.t[i]),
                elapsed_approach=float(c.t[i]-c.t[start]), reverse_lag=reverse,
                initial_opponent_toward=float(c.toward[i, opp]),
                pre_opponent_acceleration=float(c.toward[i, opp]-c.toward[i-half, opp]),
                maximum_ball_impulse=float(np.max(impulse)),
                primary_unavailable='Large-ball-impulse exclusion threshold is unspecified.'))
            if pause:
                qualified, start, run = None, None, 0
    return rows


def _late_widest_path(defenders, ball, nx=33, ny=21):
    """Exact maximin path with horizontal/downward eight-neighbor edges only."""
    xs, ys = np.linspace(-4096., 4096., nx), np.linspace(-5120., 0., ny)
    grid = np.stack(np.meshgrid(xs, ys), axis=-1)
    clearance = np.min(np.linalg.norm(grid[:, :, None, :]-defenders[None, None, :, :], axis=-1), axis=-1)
    ix, iy = int(np.argmin(abs(xs-ball[0]))), int(np.argmin(abs(ys-ball[1])))
    prev = np.full(nx, -np.inf)
    prev[ix] = clearance[iy, ix]
    for row in range(iy, -1, -1):
        if row != iy:
            padded = np.pad(prev, (1, 1), constant_values=-np.inf)
            prev = np.minimum(clearance[row], np.maximum.reduce([padded[:-2], padded[1:-1], padded[2:]]))
        for j in range(1, nx):
            prev[j] = max(prev[j], min(prev[j-1], clearance[row, j]))
        for j in range(nx-2, -1, -1):
            prev[j] = max(prev[j], min(prev[j+1], clearance[row, j]))
    return float(prev[nx//2]), float(np.mean(clearance > 600))


def B12(c):
    """Widest-path open/closed exposure, requiring audited first-concession outcome.
    Null controls nearest defender, heading, coverage, boost; series-cross-fitted
    standardized risk difference with whole-series bootstrap CI/centered p.
    """
    rows = []
    for i in c.anchors(.3, 0.):
        ball = c.a['ball'][i]
        if not (-4800 <= ball[1] <= -300 and ball[2] < 300):
            continue
        defenders = c.a['players'][i, :3, :2]
        w, coverage = _late_widest_path(defenders, ball[:2])
        coarse, _ = _late_widest_path(defenders, ball[:2], 17, 11)
        rows.append(c.row(i, x=int(w > 600), y=None, widest_clearance=w,
            widest_clearance_coarse=coarse, uncovered_grid_fraction=coverage,
            nearest_defender=float(np.min(c.dist[i, :3])),
            goal_side_count=int(np.sum(defenders[:, 1] < ball[1])),
            ball_heading=float(np.arctan2(ball[4], ball[3])),
            ball_speed=float(np.linalg.norm(ball[3:5])),
            primary_unavailable='Complete terminal-goal retention/censoring audit unavailable.'))
    return rows


def B13(c):
    """Prospective area histories, not substituted for train-fitted residual rho.
    Exact primary needs 6s lag-.2 residual autocorrelation and audited goal labels;
    match present area/threat/variance and bootstrap whole series.
    """
    rows = []
    p = c.a['players'][:, :3, :2]
    d, e = p[:, 1]-p[:, 0], p[:, 2]-p[:, 0]
    area = np.abs(d[:, 0]*e[:, 1]-d[:, 1]*e[:, 0])/2
    logarea = np.log(area+10000.)
    step = max(1, int(round(.2*c.fps)))
    for i in c.anchors(8., 0., spacing=9.):
        indices = np.arange(c.idx(i, -6.), i+1, step)
        players = c.a['players'][indices, :3]
        contexts = np.column_stack([c.a['ball'][indices], players[:, :, :2].mean(axis=1),
            players[:, :, 3:6].mean(axis=1), players[:, :, 6],
            c.a['remaining'][indices], c.a['score_diff'][indices], c.a['overtime'][indices]])
        rows.append(c.row(i, x=None, y=None, current_area=float(area[i]),
            log_area_history=logarea[indices].tolist(), area_context_history=contexts.tolist(),
            history_times=(c.t[indices]-c.t[i]).tolist(),
            primary_unavailable='Requires train-fitted residual area and audited first-concession labels.'))
    return rows


def B14(c):
    """Frozen front/rear response blocks for matched cross-series excess slope null.
    Stable ordering is primary; other rows are onset-identity sensitivity only.
    """
    rows, candidates = [], []
    raw, v = c.a['ball'][:, 3], _late_velocity(c)
    k = max(1, int(round(.3*c.fps)))
    for i in range(k+1, len(raw)-k):
        if not c.ok(i, .5, 1.):
            continue
        old, new = np.sign(raw[i-1]), np.sign(raw[i])
        if old == 0 or new == 0 or old == new:
            continue
        if not (np.all(np.sign(raw[i-k-1:i]) == old) and np.all(np.sign(raw[i:i+k+1]) == new)):
            continue
        impulse = raw[c.idx(i, .2)]-raw[c.idx(i, -.1)]
        if abs(impulse) >= 800:
            candidates.append((i, float(impulse)))
    last = -np.inf
    for j, (i, impulse) in enumerate(candidates):
        if c.t[i]-last < 1.:
            continue
        if j+1 < len(candidates) and c.t[candidates[j+1][0]]-c.t[i] < 1.:
            continue
        last = c.t[i]
        order = np.argsort(-c.a['players'][i, :3, 1], kind='stable')
        end = c.idx(i, .8)
        stable = bool(np.all(np.argsort(-c.a['players'][i:end+1, :3, 1], axis=1, kind='stable') == order))
        response = np.mean(v[c.idx(i, .3):end+1, :3, 0], axis=0)-np.mean(v[c.idx(i, -.5):i+1, :3, 0], axis=0)
        rows.append(c.row(i, x=float(response[order[0]]), y=float(response[order[2]]),
            front_response=float(response[order[0]]), rear_response=float(response[order[2]]),
            middle_response=float(response[order[1]]), stable_order=stable, ball_impulse=impulse,
            starting_vx=v[i, :3, 0].tolist(), y_spacing=np.diff(c.a['players'][i, order, 1]).tolist(),
            reversal_path=raw[c.idx(i, -.3):c.idx(i, .3)+1].tolist(),
            front_block=v[c.idx(i,-.5):end+1,order[0],0].tolist(),
            rear_block=v[c.idx(i,-.5):end+1,order[2],0].tolist()))
    return rows


def _late_pulses(c, own=True):
    distance = np.min(c.dist[:, :3] if own else c.dist[:, 3:], axis=1)
    pulses = np.zeros(len(c.t), bool)
    run, armed, last, segprev = 0, False, -np.inf, None
    k = max(1, int(round(.3*c.fps)))
    for i in range(len(c.t)):
        seg = c.a['segment'][i]
        if seg < 0 or seg != segprev:
            run, armed, last = 0, False, -np.inf
        segprev = seg
        if seg < 0 or not np.isfinite(distance[i]):
            continue
        run = run+1 if distance[i] > 1200 else 0
        if run >= k+1:
            armed = True
        if armed and distance[i] < 800 and c.t[i]-last >= .5:
            pulses[i] = True
            armed, last = False, c.t[i]
    return pulses


def B15(c):
    """Past-only pulse-history rows for fitted phase hazards, with complete blocks.
    Primary needs matched-history randomization of complete fitted joint sin/cos
    procedure and whole-series excess-modulation intervals. Raw modulation is biased.
    """
    own, opp = _late_pulses(c, True), _late_pulses(c, False)
    rows, histories, counts, segprev = [], [[], []], [0, 0], None
    for i in range(len(c.t)-1):
        seg = c.a['segment'][i]
        if seg < 0 or seg != segprev:
            histories, counts = [[], []], [0, 0]
        segprev = seg
        for side, pulse in enumerate((own, opp)):
            if pulse[i]:
                histories[side].append(i)
                histories[side] = histories[side][-4:]
                counts[side] += 1
        if min(map(len, histories)) < 4:
            continue
        history_seconds = float(c.t[i]-min(c.t[histories[0][0]], c.t[histories[1][0]]))
        if not c.ok(i, history_seconds, .1):
            continue
        intervals = [np.diff(c.t[h]) for h in histories]
        if any(np.any((d < .8) | (d > 4.)) for d in intervals):
            continue
        periods = [float(np.median(d)) for d in intervals]
        phases = [2*np.pi*((c.t[i]-c.t[h[-1]]) % period)/period for h, period in zip(histories, periods)]
        j = c.idx(i, .1)
        rows.append(c.row(i, x=float(phases[1]), y=int(np.any(own[i+1:j+1])),
            own_phase=float(phases[0]), opponent_phase=float(phases[1]),
            own_period=periods[0], opponent_period=periods[1],
            own_history=(c.t[histories[0]]-c.t[i]).tolist(),
            opponent_history=(c.t[histories[1]]-c.t[i]).tolist(),
            own_pulse_count=counts[0], opponent_pulse_count=counts[1],
            own_pulse_now=int(own[i]), opponent_pulse_now=int(opp[i]),
            history_block=f'{seg}:{int(c.t[i]//12)}'))
    return rows


def B16(c):
    """Only earlier nonoverlapping prefix occurrences establish an expected ending.
    Latency anchor is ending completion; observe 1.3s to sustain onset through1s.
    Null matches actual turn and strictly earlier history; series-bootstrap contrast.
    """
    rows, p = [], c.a['players']
    stride, sustain = max(1, int(round(.5*c.fps))), max(1, int(round(.3*c.fps)))
    for player in range(3):
        history = {}
        for seg in np.unique(c.a['segment'][c.a['segment'] >= 0]):
            indices = np.flatnonzero(c.a['segment'] == seg)
            points = np.arange(indices[0], indices[-1]+1, stride)
            if len(points) < 5:
                continue
            delta = np.diff(p[points, player, 0])
            symbols = np.where(delta < -150, -1, np.where(delta > 150, 1, 0))
            for j in range(3, len(symbols)):
                begin, onset, anchor = points[j-3], points[j], points[j+1]
                prefix, ending = tuple(int(v) for v in symbols[j-3:j]), int(symbols[j])
                packed, stop = [], -np.inf
                for old in history.get(prefix, []):
                    if old[0] >= stop and old[1] <= c.t[begin]:
                        packed.append(old)
                        stop = old[1]
                expected = None
                if len(packed) >= 3:
                    values, counts = np.unique([x[2] for x in packed], return_counts=True)
                    best = int(np.argmax(counts))
                    if counts[best]/sum(counts) >= .75:
                        expected = int(values[best])
                variation = expected is not None and ending != expected and ending != 0
                control = expected is None and ending != 0
                if (variation or control) and c.ok(anchor, 2., 1.3):
                    route = slice(begin, anchor+1)
                    if np.all(c.dist[route, player] < 2000) and np.all(c.toward[route, player] > 300):
                        opp = 3+int(np.argmin(np.linalg.norm(p[onset, 3:, :2]-p[onset, player, :2], axis=1)))
                        latency = 1.
                        for k in range(anchor, c.idx(anchor, 1.)+1):
                            vx = p[k:k+sustain+1, opp, 3]
                            if len(vx) == sustain+1 and np.all(ending*vx >= 200):
                                latency = min(1., float(c.t[k]-c.t[anchor]))
                                break
                        rows.append(c.row(anchor, x=int(variation), y=latency,
                            player=player, frozen_opponent=opp, prefix=list(prefix), ending=ending,
                            match_unit=str(parsed_json(c.m.get("player_ids"), [None]*6)[player])+":"+str(ending),
                            previous_occurrences=len(packed), expected_ending=expected,
                            actual_turn_delta_x=float(delta[j]),
                            pre_anchor_alignment=bool(ending*p[anchor, opp, 3] >= 200),
                            prealigned=int(ending*p[anchor, opp, 3] >= 200),
                            opponent_start_vx=float(p[anchor, opp, 3]),
                            timing_validation='raw30Hz_validation_required_before_scaling'))
                if c.ok(anchor, 2., 0.) and np.all(c.dist[begin:anchor+1, player] < 2000) and np.all(c.toward[begin:anchor+1, player] > 300):
                    history.setdefault(prefix, []).append((float(c.t[begin]), float(c.t[anchor]), ending))
    return rows


def B17(c):
    """Shapes only: no permitted same-season 2025 opponent-exposure reference fit.
    Primary is rarity interaction coefficient, exposure-aware whole-series bootstrap.
    """
    rows = []
    for i in c.anchors(.3, 0.):
        p = c.a['players'][i, :3]
        width, depth = float(np.ptp(p[:, 0])), float(np.ptp(p[:, 1]))
        shape = int(width >= 2500)*2+int(depth >= 2500)
        rows.append(c.row(i, x=shape, y=None, width=width, depth=depth,
            primary_unavailable='No permitted same-season reference fit for 2025 validation.'))
    return rows


def B18(c):
    """Sectors only: no permitted same-season other-roster player-habit fit.
    Exact null uses complete-block pseudo-trios and shared-player/roster/series
    multiway uncertainty, maximum p-value and hull of dependency-aware intervals.
    """
    rows = []
    for i in c.anchors(.3, 0.):
        relative = c.a['players'][i, :3, :2]-c.a['ball'][i, :2]
        lateral = np.where(relative[:, 0] < -600, 0, np.where(relative[:, 0] > 600, 2, 1))
        sectors = lateral*2+(relative[:, 1] >= 0)
        rows.append(c.row(i, x=None, y=None, sectors=sectors.tolist(),
            observed_complementarity=int(len(np.unique(sectors)) == 3),
            primary_unavailable='No permitted same-season other-roster habit fit for 2025 validation.'))
    return rows

# Model-free matched contrasts and whole-series inference.
def bh18(pvalues):
    """BH over exactly B01..B18; missing/undefined primary tests enter as p=1."""
    ids = [f"B{i:02d}" for i in range(1, 19)]
    if not isinstance(pvalues, dict):
        if len(pvalues) != 18:
            raise ValueError("BH family must contain exactly 18 tests")
        pvalues = dict(zip(ids, pvalues))
    if set(pvalues) - set(ids):
        raise ValueError("Unexpected primary ID")
    ps = np.asarray([pvalues.get(k) if pvalues.get(k) is not None else 1.
                     for k in ids], dtype=float)
    ps[~np.isfinite(ps)] = 1.
    if np.any((ps < 0) | (ps > 1)):
        raise ValueError("p-values must be in [0,1]")
    order = np.argsort(ps, kind="stable")
    adjusted = np.minimum.accumulate(
        (18 * ps[order] / np.arange(1, 19))[::-1])[::-1].clip(0, 1)
    out = np.empty(18)
    out[order] = adjusted
    return dict(zip(ids, out.tolist()))


def _scri_empty(reason, n_events=0, n_series=0, details=None):
    return {"effect": None, "ci95": [None, None], "p": None,
            "n_series": int(n_series), "n_events": int(n_events),
            "reason": reason, "details": details or {}}


def _scri_interval(effect, draws):
    draws = np.asarray(draws, float)
    draws = draws[np.isfinite(draws)]
    if not len(draws):
        return {"ci95": [None, None], "p": None, "valid_replicates": 0}
    ci = np.quantile(draws, [.025, .975]).tolist()
    p = (1 + np.count_nonzero(np.abs(draws - effect) >= abs(effect))) / (1 + len(draws))
    if np.ptp(draws) < 1e-12 and abs(effect) > 1e-12:
        p = None  # Degenerate estimated variance does not prove a population effect.
    return {"ci95": ci, "p": None if p is None else float(p),
            "valid_replicates": int(len(draws))}


def series_inference(series_rows, seed=42, reps=2000):
    """Equal-series estimator with whole-series and crossed-roster resampling.

    Each input row aggregates both perspectives and all games. Shared-roster
    sensitivity is a crossed series/roster pigeonhole bootstrap: an entire
    series receives its series multiplicity times its participants' shared
    roster multiplicities. No frame/window is independently resampled.
    """
    import hashlib
    good = [r for r in series_rows
            if r.get("effect") is not None and np.isfinite(r["effect"])]
    if len({str(r["series_id"]) for r in good}) != len(good):
        raise ValueError("Expected one aggregate per series")
    values = np.asarray([r["effect"] for r in good], float)
    n = len(values)
    if n < 2:
        return _scri_empty("Fewer than two independent matched series",
                          sum(r.get("n_events", 0) for r in good), n)
    rng = np.random.default_rng(seed)
    effect = float(values.mean())
    draws = np.empty(reps)
    for start in range(0, reps, 256):
        count = min(256, reps - start)
        draws[start:start + count] = values[rng.integers(0, n, (count, n))].mean(axis=1)
    result = dict(effect=effect, **_scri_interval(effect, draws),
                  n_series=n, n_events=int(sum(r.get("n_events", 0) for r in good)))
    events = {}
    for i, row in enumerate(good):
        if row.get("event"):
            events.setdefault(str(row["event"]), []).append(i)
    event_draws = []
    if len(events) >= 2 and sum(map(len, events.values())) == n:
        blocks = list(events.values())
        for _ in range(reps):
            picked = rng.integers(0, len(blocks), len(blocks))
            ix = np.concatenate([blocks[j] for j in picked])
            event_draws.append(float(values[ix].mean()))
    event_result = _scri_interval(effect, event_draws)
    event_result.update(n_clusters=len(events), interpretation="Full group_path diagnostic; hierarchy unverified",
                        certified_event_resampling=False)
    rosters = sorted({str(rid) for row in good for rid in row.get("roster_ids", ())
                      if rid is not None and str(rid)})
    lookup = {rid: j for j, rid in enumerate(rosters)}
    participants = [[lookup[str(rid)] for rid in dict.fromkeys(row.get("roster_ids", ()))
                     if str(rid) in lookup] for row in good]
    crossed = []
    if len(rosters) >= 2 and all(participants):
        for _ in range(reps):
            sw = rng.multinomial(n, np.full(n, 1 / n)).astype(float)
            rw = rng.multinomial(len(rosters), np.full(len(rosters), 1 / len(rosters)))
            weights = sw * np.asarray([np.prod(rw[ix]) for ix in participants])
            if weights.sum() > 0:
                crossed.append(float(np.dot(weights, values) / weights.sum()))
    crossed_result = _scri_interval(effect, crossed)
    crossed_result.update(n_rosters=len(rosters),
                         method="Crossed series x shared-participant-roster pigeonhole bootstrap",
                         interpretation="Descriptive sensitivity")
    order = sorted(range(n), key=lambda i: hashlib.sha256(
        f"{seed}:{good[i]['series_id']}".encode()).digest())
    halves = [float(values[order[k::2]].mean()) if len(order[k::2]) else None for k in (0, 1)]
    leave_event = {key: float(np.delete(values, ix).mean())
                   for key, ix in events.items() if len(ix) < n}
    primary_pass = result["p"] is not None and result["p"] <= .01 and result["ci95"][0] > 0
    sensitivity_pass = all(s["p"] is not None and s["p"] <= .01 and s["ci95"][0] > 0
                           for s in (event_result, crossed_result))
    result["details"] = {
        "resampling_unit": "series; both perspectives/all games/complete event blocks retained",
        "bootstrap_replicates": reps, "series_equal_weight": True,
        "team_series_equal_weight_before_series_mean": True,
        "half_effects": halves, "halves_positive": all(x is not None and x > 0 for x in halves),
        "event_sensitivity": event_result, "roster_series_sensitivity": crossed_result,
        "leave_one_event_out_effects": leave_event,
        "sensitivity_changes_primary_pass": bool(primary_pass and not sensitivity_pass),
        "series_effects": [{"series_id": r["series_id"], "effect": r["effect"],
                           "n_events": r.get("n_events", 0)} for r in good]}
    return result


def _scri_match_rows(rows, idea, rms_caliper=.20, coordinate_caliper=.25):
    """Fixed physical-distance optimal 1:1 matching, never selected by outcomes."""
    from scipy.optimize import linear_sum_assignment
    groups, invalid = {}, 0
    for row in rows:
        try:
            controls = np.asarray(row["controls"], float).reshape(-1)
            y, x = float(row["y"]), int(row["x"])
        except (KeyError, TypeError, ValueError):
            invalid += 1
            continue
        ids = (row.get("series_id"), row.get("roster_id"),
               row.get("opponent_roster_id"), row.get("region"))
        if (not len(controls) or not np.isfinite(controls).all() or not np.isfinite(y)
                or any(v is None or str(v) in ("", "nan", "None") for v in ids)):
            invalid += 1
            continue
        if idea == "B07":
            if x not in (0, 1, 2, 3):
                continue
            band, exposure = x // 2, x % 2
        else:
            band, exposure = 0, (int(x == 1) if idea == "B02" else x)
            if idea == "B02" and x not in (-1, 1):
                continue
            if exposure not in (0, 1):
                continue
        key = (*map(str, ids), str(row.get("stratum", "unknown")),
               str(row.get("match_unit", "all")), str(row.get("score_diff")), band)
        groups.setdefault(key, [[], []])[exposure].append(row)
    pairs, max_width, unmatched = [], 0, 0
    for key, (left, right) in sorted(groups.items()):
        if not left or not right:
            unmatched += len(left) + len(right)
            continue
        a = np.asarray([r["controls"] for r in left], float)
        b = np.asarray([r["controls"] for r in right], float)
        if a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[1]:
            invalid += len(left) + len(right)
            continue
        delta = b[:, None, :] - a[None, :, :]
        rms = np.sqrt(np.mean(delta ** 2, axis=2))
        eligible = (rms <= rms_caliper) & (np.max(np.abs(delta), axis=2) <= coordinate_caliper)
        aball = np.asarray([r["ball"] for r in left])
        bball = np.asarray([r["ball"] for r in right])
        caps = np.array([600,600,300,600,600,600], float)
        eligible &= np.all(np.abs(bball[:,None,:]-aball[None,:,:]) <= caps, axis=2)
        if not eligible.any():
            unmatched += len(left) + len(right)
            continue
        # Large penalty gives max-cardinality then minimum-distance assignment.
        positive, negative = linear_sum_assignment(np.where(eligible, rms, 1e6))
        count = 0
        for ib, ia in zip(positive, negative):
            if not eligible[ib, ia]:
                continue
            positive_row, negative_row = right[ib], left[ia]
            pairs.append({"series_id": key[0], "roster_id": key[1],
                          "opponent_roster_id": key[2], "band": key[-1],
                          "event": positive_row.get("event"),
                          "positive": positive_row, "negative": negative_row,
                          "difference": float(positive_row["y"] - negative_row["y"]),
                          "controls_difference": delta[ib, ia].tolist(),
                          "distance": float(rms[ib, ia])})
            max_width = max(max_width, a.shape[1])
            count += 1
        unmatched += len(left) + len(right) - 2 * count
    return pairs, {"valid_matched_pairs": len(pairs), "unmatched_events": unmatched,
                   "invalid_or_missing_context_events": invalid,
                   "fixed_rms_caliper": rms_caliper,
                   "fixed_coordinate_caliper": coordinate_caliper,
                   "controls_dimension": max_width,
                   "matching": "Optimal 1:1 without replacement; exact within-series roster/opponent/region/phase",
                   "controls_scale": "Caller-supplied fixed physical units; no validation scale estimates"}


def _scri_series_from_pairs(pairs, idea, value_key="y"):
    team_bands = {}
    for pair in pairs:
        a, b = pair["positive"], pair["negative"]
        try:
            value = float(a[value_key]) - float(b[value_key])
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(value):
            continue
        key = (pair["series_id"], pair["roster_id"], pair["band"])
        team_bands.setdefault(key, []).append((value, pair))
    teams = {}
    for (sid, roster, band), items in team_bands.items():
        teams.setdefault((sid, roster), {})[band] = (
            float(np.mean([x[0] for x in items])), [x[1] for x in items])
    series = {}
    for (sid, roster), bands in teams.items():
        if idea == "B07":
            if set(bands) != {0, 1}:
                continue
            effect, used = bands[1][0] - bands[0][0], bands[0][1] + bands[1][1]
        else:
            effect, used = bands[0]
        series.setdefault(sid, []).append((effect, used))
    out = []
    for sid, items in sorted(series.items()):
        used = [p for _, pairs_ in items for p in pairs_]
        rosters = sorted({p[k] for p in used for k in ("roster_id", "opponent_roster_id")})
        events = {str(p.get("event")) for p in used if p.get("event")}
        out.append({"series_id": sid, "effect": float(np.mean([x[0] for x in items])),
                    "n_events": 2 * len(used), "roster_ids": rosters,
                    "event": next(iter(events)) if len(events) == 1 else None,
                    "n_team_series": len(items)})
    return out


def matched_screen(train, val, idea, seed=42, reps=2000):
    """Exact matched contrast for B02/B07/B10/B11/B16, followed by series inference.

    Fixed model-free matching has no fitted nuisance. Val evaluates a frozen
    rule; no train row contributes to the test statistic. Restrict to the
    specified within-series first choice and report lost overlap.
    """
    if idea not in ("B02", "B07", "B10", "B11", "B16"):
        raise ValueError(f"{idea} does not have a matched-contrast estimand")
    if any(r.get("split") != "train" for r in train):
        raise ValueError("Nontraining row supplied to training partition")
    if any(r.get("split") != "val" or r.get("season") != "rlcs-2025" for r in val):
        raise ValueError("Only 2025 val rows may enter test statistics")
    pairs, diagnostics = _scri_match_rows(val, idea)
    result = series_inference(_scri_series_from_pairs(pairs, idea), seed, reps)
    result.setdefault("details", {}).update(diagnostics)
    result["details"].update(
        estimand=("Within-series ambiguity-by-separation probability interaction"
                  if idea == "B07" else "Within-series matched exposed-minus-control contrast"),
        n_train_events=len(train), n_validation_candidates=len(val),
        train_usage="None: fixed-rule, model-free matching; no val-fitted nuisance",
        no_cross_series_extrapolation=True,
        strength_adjustment="Exact same opponent and focal roster within series",
        null="Zero conditional matched contrast")
    if pairs:
        delta = np.asarray([p["controls_difference"] for p in pairs])
        result["details"]["mean_absolute_control_gap"] = np.mean(np.abs(delta), axis=0).tolist()
        result["details"]["mean_signed_control_gap"] = delta.mean(axis=0).tolist()
        result["details"]["max_matched_distance"] = max(p["distance"] for p in pairs)
    if idea == "B07":
        retained = {r["series_id"] for r in _scri_series_from_pairs(pairs, idea)}
        cells = {str(cell): {"n_events": 0, "series": set()} for cell in range(4)}
        for pair in pairs:
            if pair["series_id"] not in retained:
                continue
            for side in ("positive", "negative"):
                row = pair[side]
                cell = cells[str(int(row["x"]))]
                cell["n_events"] += 1
                cell["series"].add(pair["series_id"])
        result["details"]["cells"] = {k: {"n_events": v["n_events"], "n_series": len(v["series"])}
                                       for k, v in cells.items()}
    for key in ("pretrend", "frozen_lane", "reverse_y", "prealigned"):
        if any(key in p["positive"] and key in p["negative"] for p in pairs):
            control = series_inference(_scri_series_from_pairs(pairs, idea, key), seed + 19, reps)
            for name in ("p", "valid_replicates", "details"):
                control.pop(name, None)
            result["details"][key + "_contrast"] = control
    return result


def calibration_sanity(rows_by_idea, seed=42, repeats=96):
    """Whole-series label-shuffle rank unit check on smoke B02/B10 outcomes.

    Conservative p-values are discrete with <=6 replays. Randomized-tie rank
    is reported separately as a Uniform(0,1) implementation check, NOT as
    calibration evidence for the observational screens or nuisance models.
    """
    import itertools
    rng, output = np.random.default_rng(seed), {}
    for idea in ("B02", "B10"):
        blocks = {}
        for row in rows_by_idea.get(idea, []):
            if row.get("split") != "val":
                continue
            try:
                value = float(row.get("y"))
            except (TypeError, ValueError):
                continue
            if np.isfinite(value) and row.get("series_id"):
                blocks.setdefault(str(row["series_id"]), []).append(value)
        values = np.asarray([np.mean(v) for _, v in sorted(blocks.items())], float)
        n = len(values)
        if not n:
            output[idea] = {"status": "not_computable", "n_series": 0,
                            "reason": "No smoke validation outcome blocks"}
            continue
        if n > 12:
            raise ValueError("Smoke sanity check is bounded to <=12 series")
        signs = np.asarray(list(itertools.product((-1., 1.), repeat=n)))
        null = np.abs(signs @ values / n)
        conservative, randomized = [], []
        for _ in range(repeats):
            # Artificial +/- labels are independent of outcomes and shared by
            # every event, game and team in the same series.
            observed = abs(float(np.dot(rng.choice((-1., 1.), n), values) / n))
            tied_mask = np.isclose(null, observed, rtol=1e-10, atol=1e-12)
            larger = int(np.count_nonzero((null > observed) & ~tied_mask))
            tied = int(np.count_nonzero(tied_mask))
            conservative.append((larger + tied) / len(null))
            randomized.append((larger + rng.random() * tied) / len(null))
        mean = float(np.mean(randomized))
        rank_ok = .3 <= mean <= .7 and all(0 <= p <= 1 for p in randomized)
        # Separate synthetic unit test of the actual centered-bootstrap kernel.
        # These are artificial independent clusters sampled from the smoke
        # magnitudes, never additional observed series or screen evidence.
        simulated_p = []
        artificial_clusters, artificial_reps = 32, 399
        if np.any(np.abs(values) > 1e-12):
            for _ in range(repeats):
                synthetic = rng.choice(values, artificial_clusters) * rng.choice(
                    (-1., 1.), artificial_clusters)
                estimate = float(synthetic.mean())
                draws = synthetic[rng.integers(
                    0, artificial_clusters, (artificial_reps, artificial_clusters))].mean(axis=1)
                simulated_p.append(_scri_interval(estimate, draws)["p"])
            finite_p = np.asarray([p for p in simulated_p if p is not None], float)
            sim_mean = float(finite_p.mean()) if len(finite_p) else None
            sim_reject = float(np.mean(finite_p < .05)) if len(finite_p) else None
            synthetic_check = {
                "status": "passed" if sim_mean is not None and .3 <= sim_mean <= .7
                          and sim_reject <= .15 else "failed",
                "n_artificial_independent_clusters": artificial_clusters,
                "bootstrap_replicates": artificial_reps, "null_trials": repeats,
                "p_mean": sim_mean, "rejection_fraction_005": sim_reject,
                "p_histogram_5_bins": np.histogram(
                    finite_p, bins=np.linspace(0, 1, 6))[0].tolist(),
                "interpretation": "Synthetic zero-null cluster-label simulation using smoke-derived "
                                  "magnitudes; tests bootstrap code, not empirical calibration."}
        else:
            synthetic_check = {"status": "not_computable",
                               "reason": "All smoke series magnitudes are zero"}
        output[idea] = {
            "status": "passed" if rank_ok and synthetic_check.get("status") == "passed" else "failed", "n_series": n,
            "trials": repeats, "exact_assignments": int(len(null)),
            "control": "Independent +/- label assigned to each complete series outcome block",
            "conservative_p_mean": float(np.mean(conservative)),
            "conservative_p_histogram_5_bins": np.histogram(
                conservative, bins=np.linspace(0, 1, 6))[0].tolist(),
            "randomized_tie_rank_mean": mean,
            "randomized_tie_rank_histogram_5_bins": np.histogram(
                randomized, bins=np.linspace(0, 1, 6))[0].tolist(),
            "randomized_tie_rank_rejection_fraction_005": float(np.mean(np.asarray(randomized) < .05)),
            "uniform_rank_check": rank_ok,
            "synthetic_centered_bootstrap_check": synthetic_check,
            "limitation": "Randomized ties check rank code only; coarse conservative p-values "
                          "from few series cannot validate empirical screen calibration."}
    return output


# Matched-block gains and restricted roster-label chirality inference.

def _sg_empty(reason, rows, details=None):
    return dict(effect=None, ci95=[None, None], p=None,
                n_series=len({r["series_id"] for r in rows}), n_events=len(rows),
                reason=reason, status="not_computable", details=details or {})


def _sg_rows(rows, idea):
    kept = []
    for row in rows:
        if idea == "B14" and not row.get("stable_order"):
            continue
        try:
            z = np.asarray(row["controls"], float)
            x, y = float(row["x"]), float(row["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if (z.ndim != 1 or not len(z) or not np.isfinite(z).all()
                or not np.isfinite([x, y]).all()):
            continue
        if any(row.get(k) is None for k in ("series_id", "roster_id", "opponent_roster_id", "region")):
            continue
        kept.append(row)
    return kept


def _sg_design(rows):
    return np.column_stack((np.ones(len(rows)), np.asarray([r["controls"] for r in rows], float)))


def _sg_fit(train, targets, weights=None):
    """Fixed ridge alpha=1, physical-scaled covariates, unpenalized intercept."""
    X = _sg_design(train)
    Y = np.asarray(targets, float)
    if Y.ndim == 1:
        Y = Y[:, None]
    w = np.ones(len(train)) if weights is None else np.asarray(weights, float)
    penalty = np.eye(X.shape[1])
    penalty[0, 0] = 0.
    return np.linalg.solve(X.T @ (w[:, None] * X) + penalty,
                           X.T @ (w[:, None] * Y))


def _sg_support(train, val):
    """Training-frozen contextual overlap; no outcome or validation scale fit."""
    if not train or not val:
        return []
    from scipy.spatial import cKDTree
    T = np.asarray([r["controls"] for r in train], float)
    V = np.asarray([r["controls"] for r in val], float)
    if T.shape[1] != V.shape[1]:
        raise ValueError("Training/validation control dimensions differ")
    # Match comparable context/phase/region; season held fixed within every
    # validation contrast rather than pretending 2025 existed in training.
    groups = {}
    for i, row in enumerate(train):
        groups.setdefault((row["region"], row.get("stratum")), []).append(i)
    allowed = []
    for key in sorted(groups, key=str):
        vi = [i for i, r in enumerate(val) if (r["region"], r.get("stratum")) == key]
        if not vi:
            continue
        a, b = T[groups[key]], V[vi]
        tree = cKDTree(a)
        distance, nearest = tree.query(b, k=1)
        max_coordinate = np.max(np.abs(b-a[nearest]), axis=1)
        good = (distance / np.sqrt(T.shape[1]) <= .20) & (max_coordinate <= .25)
        allowed.extend(vi[j] for j in np.flatnonzero(good))
    return [val[i] for i in sorted(allowed)]


def _sg_clusters(rows):
    ids = sorted({r["series_id"] for r in rows})
    index = {sid: j for j, sid in enumerate(ids)}
    return ids, np.asarray([index[r["series_id"]] for r in rows], int)


def _sg_train_weights(train, rng):
    ids, ix = _sg_clusters(train)
    counts = rng.multinomial(len(ids), np.full(len(ids), 1/len(ids)))
    # Equal series in fitting, retaining every row in the sampled cluster.
    sizes = np.bincount(ix, minlength=len(ids))
    return counts[ix] / sizes[ix]


def _sg_pair_blocks(rows):
    """Disjoint complete response blocks; one fixed partner per physical series.

    A series can exchange only with one other series, including both team
    perspectives and score strata. The randomization toggles all its matched
    blocks together, retaining within-series dependence.
    """
    groups, partner = {}, {}
    for i, row in enumerate(rows):
        key = (row["season"], row["region"], row["roster_id"], row["opponent_roster_id"],
               row.get("stratum"), row["score_diff"], int(float(row["ball"][1]) >= 0))
        groups.setdefault(key, []).append(i)
    pairs = []
    for key, indices in sorted(groups.items(), key=lambda item: str(item[0])):
        remaining = list(indices)
        while len(remaining) >= 2:
            first = remaining.pop(0)
            sid = rows[first]["series_id"]
            candidates = [j for j in remaining
                          if rows[j]["series_id"] != sid
                          and (sid not in partner or partner[sid] == rows[j]["series_id"])
                          and (rows[j]["series_id"] not in partner or partner[rows[j]["series_id"]] == sid)]
            if not candidates:
                continue
            a = np.asarray(rows[first]["controls"], float)
            b = np.asarray([rows[j]["controls"] for j in candidates], float)
            difference = b-a
            rms = np.sqrt(np.mean(difference*difference, axis=1))
            ball_difference = np.abs(np.asarray([rows[j]["ball"][:6] for j in candidates])-np.asarray(rows[first]["ball"][:6]))
            good = ((rms <= .20) & (np.max(np.abs(difference), axis=1) <= .25)
                    & (ball_difference <= np.asarray([600.,600.,300.,600.,600.,600.])).all(axis=1))
            if not good.any():
                continue
            best = int(np.argmin(np.where(good, rms, np.inf)))
            other = candidates[best]
            remaining.remove(other)
            other_sid = rows[other]["series_id"]
            partner[sid], partner[other_sid] = other_sid, sid
            pairs.append((first, other))
    return np.asarray(pairs, int).reshape((-1, 2))


def _sg_ridge_cache(train, targets):
    """Per-series sufficient statistics; bootstrap never recomputes dense designs."""
    X, Y = _sg_design(train), np.asarray(targets, float)
    if Y.ndim == 1:
        Y = Y[:, None]
    ids, ix = _sg_clusters(train)
    a, b = [], []
    for j in range(len(ids)):
        z, y = X[ix == j], Y[ix == j]
        a.append(z.T @ z / len(z))
        b.append(z.T @ y / len(z))
    penalty = np.eye(X.shape[1])
    penalty[0,0] = 0.
    return np.asarray(a), np.asarray(b), penalty


def _sg_cached_fit(cache, counts=None):
    a, b, penalty = cache
    weights = np.ones(len(a)) if counts is None else np.asarray(counts, float)
    return np.linalg.solve(np.tensordot(weights, a, axes=1)+penalty,
                           np.tensordot(weights, b, axes=1))


def _sg_boot_fit(cache, rng):
    n = len(cache[0])
    return _sg_cached_fit(cache, rng.multinomial(n, np.full(n, 1/n)))


def _sg_gain(rows, residual, pairs, swap=None, series_weights=None, sign=1.):
    """Averaging team-series slopes before equal-series means avoids frame tests."""
    if not len(pairs):
        return None, []
    a, b = pairs[:, 0], pairs[:, 1]
    swap = np.zeros(len(pairs), bool) if swap is None else np.asarray(swap, bool)
    source = np.r_[a, b]
    donor = np.r_[np.where(swap, b, a), np.where(swap, a, b)]
    cells = {}
    for index, recipient in zip(source, donor):
        row = rows[int(index)]
        key = (row["series_id"], row["roster_id"])
        cells.setdefault(key, []).append((residual[index, 0], residual[recipient, 1]))
    by_series = {}
    for (sid, roster), points in cells.items():
        z = np.asarray(points, float)
        if len(z) < 3:
            continue
        x, y = z[:, 0]-z[:, 0].mean(), z[:, 1]-z[:, 1].mean()
        denominator = float(x @ x)
        if denominator <= 1e-12:
            continue
        by_series.setdefault(sid, []).append(sign * float(x @ y) / denominator)
    if not by_series:
        return None, []
    summaries = [{"series_id": sid, "effect": float(np.mean(value))}
                 for sid, value in sorted(by_series.items())]
    weights = np.asarray([1. if series_weights is None else series_weights.get(r["series_id"], 0.)
                          for r in summaries])
    if weights.sum() <= 0:
        return None, summaries
    return float(np.dot(weights, [r["effect"] for r in summaries])/weights.sum()), summaries


def gain_screen(train, val, idea, seed=42, reps=2000):
    """B01/B14 observed-minus-repaired gain with conditional block randomization.

    Each permutation swaps all complete receiver blocks of an entire matched
    series pair together, preserving within-series dependence. Statistic is gain(assignment)-gain(complement assignment), giving the
    specified observed-minus-other-series control and a two-sided paired null.
    Bootstrap resamples full training and validation series, refits nuisance,
    and reconstructs the block match in the resampled validation clusters.
    """
    if idea not in ("B01", "B14"):
        raise ValueError(idea)
    if any(r.get("split") != "train" for r in train) or any(r.get("split") != "val" or r.get("season") != "rlcs-2025" for r in val):
        raise ValueError("Training-only fitting and 2025-only test required")
    train, candidates = _sg_rows(train, idea), _sg_rows(val, idea)
    val = _sg_support(train, candidates)
    detail = {"n_train_events": len(train), "n_val_candidates": len(candidates),
              "n_common_support": len(val), "n_common_support_excluded": len(candidates)-len(val),
              "null": "Complete receiver-response blocks swapped within same-roster/opponent cross-series context-matched pairs",
              "strength_adjustment": "Exact same focal/opponent roster donor matching",
              "nuisance": "Train-only fixed-alpha ridge; bootstrap refits with whole-series multiplicities",
              "fixed_rms_caliper": .20, "fixed_coordinate_caliper": .25,
              "resampling_unit": "Complete series with all games and both perspectives",
              "no_frame_permutation": True}
    if len({r["series_id"] for r in train}) < 2:
        return _sg_empty("Fewer than two training series for nuisance estimation", val, detail)
    pairs = _sg_pair_blocks(val)
    detail["n_exchangeable_block_pairs"] = len(pairs)
    if len(pairs) < 2:
        return _sg_empty("Fewer than two supported cross-series same-matchup response-block pairs", val, detail)
    Y = np.asarray([[r["x"], r["y"]] for r in train], float)
    ids, ix = _sg_clusters(train)
    cache = _sg_ridge_cache(train, Y)
    fit = _sg_cached_fit(cache)
    V = _sg_design(val)
    residual = np.asarray([[r["x"], r["y"]] for r in val], float)-V @ fit
    sign = -1. if idea == "B01" else 1.
    observed, summaries = _sg_gain(val, residual, pairs, sign=sign)
    control, _ = _sg_gain(val, residual, pairs, np.ones(len(pairs), bool), sign=sign)
    if observed is None or control is None or len(summaries) < 2:
        return _sg_empty("Fewer than two supported series with nondegenerate source slopes", val, detail)
    effect, rng = observed-control, np.random.default_rng(seed)
    series_pairs = [tuple(sorted((val[a]["series_id"], val[b]["series_id"]))) for a,b in pairs]
    series_pair_ids = sorted(set(series_pairs))
    series_pair_index = {key:i for i,key in enumerate(series_pair_ids)}
    permutation_groups = np.asarray([series_pair_index[key] for key in series_pairs])
    detail["n_exchangeable_series_pairs"] = len(series_pair_ids)
    permutations = []
    for _ in range(reps):
        swap = rng.integers(0, 2, len(series_pair_ids)).astype(bool)[permutation_groups]
        positive, _ = _sg_gain(val, residual, pairs, swap, sign=sign)
        negative, _ = _sg_gain(val, residual, pairs, ~swap, sign=sign)
        if positive is not None and negative is not None:
            permutations.append(positive-negative)
    draws = []
    val_ids, val_ix = _sg_clusters(val)
    for _ in range(reps):
        fitted = _sg_boot_fit(cache, rng)
        counts = rng.multinomial(len(val_ids), np.full(len(val_ids), 1/len(val_ids)))
        selected = np.repeat(np.arange(len(val)), counts[val_ix])
        if len(selected) < 4:
            continue
        boot_rows = [val[i] for i in selected]
        boot_pairs = _sg_pair_blocks(boot_rows)
        boot_residual = np.asarray([[r["x"], r["y"]] for r in boot_rows], float)-V[selected] @ fitted
        weights = dict(zip(val_ids, counts))
        own, _ = _sg_gain(boot_rows, boot_residual, boot_pairs, series_weights=weights, sign=sign)
        other, _ = _sg_gain(boot_rows, boot_residual, boot_pairs, np.ones(len(boot_pairs), bool), weights, sign)
        if own is not None and other is not None:
            draws.append(own-other)
    p = ((1 + np.count_nonzero(np.abs(permutations) >= abs(effect)-1e-12))/(1+len(permutations))
         if permutations else None)
    ci = np.quantile(draws, [.025, .975]).tolist() if draws else [None, None]
    detail.update(observed_gain=observed, matched_null_gain=control,
                  permutation_replicates=len(permutations), valid_bootstrap_replicates=len(draws),
                  requested_replicates=reps, series_equal_weight=True,
                  n_matched_blocks=2*len(pairs),
                  block_preservation="Scalar response is an exact sufficient statistic; its complete immutable response block moves as one unit",
                  scale_sensitivities_completed=False)
    if len(draws) < .9*reps:
        p = None
        detail["bootstrap_support_failure"] = "Fewer than 90% valid whole-series bootstrap replicates"
    return dict(effect=float(effect), ci95=ci, p=None if p is None else float(p),
                n_series=len(summaries), n_events=2*len(pairs),
                status="estimated" if p is not None else "not_computable", details=detail,
                reason=None if p is not None else "Unstable resampled matched-block support")


def _sg_rho(records, residual, half, roster_subset=None, label_override=None, weights=None):
    from scipy.stats import spearmanr
    cells = {}
    for i, row in enumerate(records):
        roster = row["roster_id"] if label_override is None else label_override[i]
        if roster_subset is not None and roster not in roster_subset:
            continue
        w = 1. if weights is None else weights.get(row["series_id"], 0.)
        if w > 0:
            cells.setdefault((roster, half[row["series_id"]]), []).append((residual[i], w))
    rosters = sorted({k[0] for k in cells if (k[0], 0) in cells and (k[0], 1) in cells})
    if len(rosters) < 3:
        return None
    values = [[sum(v*w for v,w in cells[(r,h)])/sum(w for v,w in cells[(r,h)])
               for h in (0,1)] for r in rosters]
    values = np.asarray(values)
    if np.ptp(values[:, 0]) < 1e-12 or np.ptp(values[:, 1]) < 1e-12:
        return None
    return float(spearmanr(values[:, 0], values[:, 1]).statistic)


def chirality_screen(train, val, idea="B06", seed=42, reps=2000):
    """Roster split-half Spearman; restricted whole roster-series label null.

    No focal-roster/player identity enters the nuisance residualizer. Labels in
    half 1 are permuted within exact season/region/opponent strata, retaining
    each roster count. Whole-series bootstrap keeps both opponents together and
    refits training nuisance before recomputing roster means and correlation.
    """
    if any(r.get("split") != "train" for r in train) or any(r.get("split") != "val" or r.get("season") != "rlcs-2025" for r in val):
        raise ValueError("Training-only fitting and 2025-only test required")
    train, candidates = _sg_rows(train, idea), _sg_rows(val, idea)
    val = _sg_support(train, candidates)
    detail = {"n_train_events": len(train), "n_val_candidates": len(candidates),
              "n_common_support": len(val), "resampling_unit": "series, both opponents retained",
              "identity_in_nuisance": False,
              "permutation": "Half-1 whole roster-series labels within exact season/region/opponent strata; roster counts preserved",
              "scale_sensitivities_completed": False}
    if len({r["series_id"] for r in train}) < 2 or not val:
        return _sg_empty("Insufficient training or shared validation context", val, detail)
    Y = np.asarray([r["y"] for r in train], float)
    ids, ix = _sg_clusters(train)
    cache = _sg_ridge_cache(train, Y)
    fit = _sg_cached_fit(cache)
    V = _sg_design(val)
    residual = np.asarray([r["y"] for r in val])- (V @ fit).ravel()
    groups = {}
    for i, row in enumerate(val):
        groups.setdefault((row["series_id"], row["roster_id"]), []).append(i)
    records, locations = [], []
    for key, indices in sorted(groups.items()):
        row = val[indices[0]].copy()
        row["n_events"] = len(indices)
        records.append(row)
        locations.append(indices)
    series_ids = sorted({r["series_id"] for r in records}, key=lambda sid: hashlib.sha256(f"{seed}:{sid}".encode()).digest())
    half = {sid: j%2 for j,sid in enumerate(series_ids)}
    counts = {}
    for row in records:
        counts.setdefault(row["roster_id"], [0,0])[half[row["series_id"]]] += 1
    eligible = {r for r, n in counts.items() if min(n) >= 2}
    detail.update(roster_half_series_counts=counts, n_eligible_rosters=len(eligible),
                  n_scale_rosters=sum(min(n) >= 4 for n in counts.values()))
    if len(eligible) < 3:
        return _sg_empty("Fewer than three rosters with at least two independent series in each half", val, detail)
    summary = np.asarray([residual[ix].mean() for ix in locations])
    observed = _sg_rho(records, summary, half, eligible)
    if observed is None:
        return _sg_empty("Degenerate split-half roster means", val, detail)
    strata = {}
    for i,row in enumerate(records):
        if half[row["series_id"]] == 1 and row["roster_id"] in eligible:
            strata.setdefault((row["season"], row["region"], row["opponent_roster_id"]), []).append(i)
    exchange = [indices for indices in strata.values()
                if len({records[i]["roster_id"] for i in indices}) >= 2]
    moving = {records[i]["roster_id"] for indices in exchange for i in indices}
    detail.update(n_exchangeable_strata=len(exchange), n_exchangeable_rosters=len(moving))
    rng = np.random.default_rng(seed)
    permutations, draws = [], []
    labels = np.asarray([r["roster_id"] for r in records], object)
    # All evaluated rosters must participate in a genuine restricted label move.
    if exchange and eligible <= moving:
        for _ in range(reps):
            shuffled = labels.copy()
            for indices in exchange:
                shuffled[indices] = rng.permutation(shuffled[indices])
            value = _sg_rho(records, summary, half, eligible, shuffled)
            if value is not None:
                permutations.append(value)
    for _ in range(reps):
        fitted = _sg_boot_fit(cache, rng)
        boot_residual = np.asarray([r["y"] for r in val])-(V @ fitted).ravel()
        boot_summary = np.asarray([boot_residual[ix].mean() for ix in locations])
        sw = rng.multinomial(len(series_ids), np.full(len(series_ids), 1/len(series_ids)))
        value = _sg_rho(records, boot_summary, half, eligible, weights=dict(zip(series_ids, sw)))
        if value is not None:
            draws.append(value)
    ci = np.quantile(draws, [.025,.975]).tolist() if draws else [None,None]
    p = ((1+np.count_nonzero(np.abs(permutations)>=abs(observed)-1e-12))/(1+len(permutations))
         if permutations and len(draws)>=.9*reps else None)
    detail.update(valid_bootstrap_replicates=len(draws), permutation_replicates=len(permutations),
                  requested_replicates=reps, descriptive_correlation=observed,
                  strength_adjustment="Exact opponent strata in restricted label null",
                  nuisance="Train-only fixed-alpha ridge refit in every bootstrap; no focal identities")
    retained = [r for r in records if r["roster_id"] in eligible]
    return dict(effect=observed, ci95=ci, p=None if p is None else float(p),
                n_series=len({r["series_id"] for r in retained}),
                n_events=sum(r["n_events"] for r in retained),
                status="estimated" if p is not None else "not_computable", details=detail,
                reason=None if p is not None else "Split-half effect estimable, but restricted roster-label exchangeability or bootstrap support is insufficient")


# BEGIN PREDICTION METHODS
# Train-only prediction screens. scipy is deliberately used instead of sklearn.
# This fragment expects numpy as np and inference helpers from screen.py.

def _model_missing(reason, details=None):
    details = details or {}
    return {"effect": None, "ci95": [None, None], "p": None,
            "n_series": details.get("supported_val_series", 0),
            "n_events": details.get("numeric_and_proximity_supported_val_rows", 0),
            "reason": reason, "details": details}


# Caches keep strong row-list references to prevent Python id reuse.
# Row lists are immutable throughout a prediction_screen call.
_MODEL_BOOST_CACHE = {}
_MODEL_AGGREGATE_CACHE = {}


def _model_boost_metadata(rows):
    cached = _MODEL_BOOST_CACHE.get(id(rows))
    if cached is not None and cached[0] is rows:
        return cached[1]
    minimum = np.full(len(rows), np.inf)
    maximum = np.full(len(rows), -np.inf)
    count = np.zeros(len(rows), np.int64)
    at_maximum = np.zeros(len(rows), np.int64)
    names = sorted({str(row["series_id"]) for row in rows})
    lookup = {sid: i for i, sid in enumerate(names)}
    series = np.asarray([lookup[str(row["series_id"])] for row in rows], int)
    for i, row in enumerate(rows):
        players = np.asarray(row.get("players", row.get("initial_state", [])), float)
        history = np.asarray(row.get("boost_history", []), float)
        if players.shape != (6, 7):
            continue
        values = np.r_[players[:, 6], history.ravel()]
        values = values[np.isfinite(values)]
        if len(values):
            minimum[i], maximum[i], count[i] = values.min(), values.max(), len(values)
            tolerance = max(1e-5, abs(maximum[i]) * 1e-6)
            at_maximum[i] = np.count_nonzero(np.abs(values - maximum[i]) <= tolerance)
    metadata = (minimum, maximum, count, at_maximum, series)
    _MODEL_BOOST_CACHE[id(rows)] = (rows, metadata)
    return metadata


def _model_boost_scale(rows, weights=None, require_saturation=False):
    """Train-only raw maximum/saturation, cached once per immutable row set."""
    low, high, count, at_own_max, series = _model_boost_metadata(rows)
    active = count > 0
    if weights is not None:
        active &= np.asarray(weights) > 0
    if not active.any():
        return None, {"reason": "No finite training boost"}
    maximum, minimum = float(high[active].max()), float(low[active].min())
    tolerance = max(1e-5, abs(maximum) * 1e-6)
    candidates = active & (high >= maximum - tolerance)
    at_max = np.where(candidates, at_own_max, 0).copy()
    # Integer replay boost usually has exact repeated maxima. Preserve exact
    # tolerance semantics for custom noninteger values with this rare fallback.
    for i in np.flatnonzero(candidates & (high != maximum)):
        row = rows[i]
        players = np.asarray(row.get("players", row.get("initial_state", [])), float)
        history = np.asarray(row.get("boost_history", []), float)
        values = np.r_[players[:, 6], history.ravel()]
        at_max[i] = np.count_nonzero(np.isfinite(values) &
                                    (np.abs(values - maximum) <= tolerance))
    fraction = float(at_max.sum() / count[active].sum())
    saturated_series = len(np.unique(series[at_max > 0]))
    audit = {"raw_minimum": minimum, "raw_maximum": maximum,
             "saturation_fraction": fraction, "saturation_series": saturated_series,
             "scale_source": "Training observations only; observed repeated upper saturation"}
    credible = maximum > 0 and minimum >= -tolerance
    if require_saturation:
        credible &= fraction >= .005 and saturated_series >= 2
    audit["verified"] = bool(credible)
    return (maximum if credible else None), audit


def _model_numeric(row, idea, boost_scale, reflect=False):
    """Declared physical scaling, no validation standardization or tuning."""
    pscale = np.array([4096., 5120., 2044., 2300., 2300., 2300., boost_scale])
    bscale = pscale[:6]
    psign = np.array([-1., 1., 1., -1., 1., 1., 1.]) if reflect else np.ones(7)
    bsign = psign[:6]
    context = np.array([
        float(row["score_diff"]), float(row["remaining"]) / 300.,
        (float(row["remaining"]) / 300.) ** 2,
        (float(row["remaining"]) / 300.) ** 3,
        float(row["overtime"]), float(row["ot_duration"]) / 300.,
        min(float(row["segment_age"]), 300.) / 300.])
    if idea == "B04":
        p = np.asarray(row["players"], float)
        hp = np.asarray(row["past_players"], float)
        hb = np.asarray(row["past_ball"], float)
        focal = int(row["x"])
        base = np.r_[(p / pscale * psign).ravel(),
                     (hp[:, focal, :] / pscale * psign).ravel(),
                     (hb / bscale * bsign).ravel(), context]
        own = (np.asarray(row["teammate_features"], float).reshape(-1, 7) /
               pscale * psign).ravel()
        other = (np.asarray(row["opponent_features"], float).reshape(-1, 7) /
                 pscale * psign).ravel()
        y = int(row["y"])
        if reflect:
            y = 2 - y
    else:
        p = np.asarray(row["initial_state"], float)
        hb = np.asarray(row["ball_history"], float)
        boost_history = np.asarray(row["boost_history"], float)
        base = np.r_[(p / pscale).ravel(), (hb / bscale).ravel(),
                     (boost_history / boost_scale).ravel(), context]
        own = other = np.empty(0)
        y = (np.asarray(row["future_boost"], float) / boost_scale < .20).astype(int)
    # Common support concerns the present context, not the target or future boost.
    ball = np.asarray(row["ball"], float)
    support = np.r_[ball / bscale, p[:, :3].mean(axis=0) / pscale[:3],
                    np.linalg.norm(p[:, 3:5], axis=1).mean() / 2300.,
                    p[:, 6].mean() / boost_scale, context[[0, 1, 4, 5]]]
    return base, own, other, y, support


def _model_prepare(train, val, idea, boost_scale, reflect=False):
    from scipy import sparse
    category_keys = ("region", "season", "event", "roster_id", "opponent_roster_id", "stratum")
    vocabulary = sorted({(key, str(r.get(key))) for r in train for key in category_keys
                         if r.get(key) is not None})
    lookup = {item: i for i, item in enumerate(vocabulary)}
    def convert(rows):
        numeric = [_model_numeric(r, idea, boost_scale, reflect) for r in rows]
        base = np.asarray([v[0] for v in numeric], float)
        own = np.asarray([v[1] for v in numeric], float)
        other = np.asarray([v[2] for v in numeric], float)
        ys = np.asarray([v[3] for v in numeric], int)
        support = np.asarray([v[4] for v in numeric], float)
        ii, jj = [], []
        for i, row in enumerate(rows):
            for key in category_keys:
                j = lookup.get((key, str(row.get(key))))
                if j is not None:
                    ii.append(i)
                    jj.append(j)
        cat = sparse.csr_matrix((np.ones(len(ii)), (ii, jj)), shape=(len(rows), len(vocabulary)))
        intercept = np.ones((len(rows), 1))
        common = sparse.hstack((intercept, base, cat), format="csr")
        xown = sparse.hstack((common, own), format="csr") if own.shape[1] else common
        xother = sparse.hstack((common, other), format="csr") if other.shape[1] else common
        return {"base": common, "own": xown, "opponent": xother,
                "y": ys, "support": support, "numeric_columns": base.shape[1]}
    return convert(train), convert(val), vocabulary


def _model_fit(x, y, weights, classes, initial=None, penalty=.1, maxiter=75):
    """Fixed-budget regularized multinomial likelihood, including binary K=2."""
    from scipy.optimize import minimize
    from scipy.special import logsumexp
    active = weights > 0
    if np.sum(active) < classes * 4 or len(np.unique(y[active])) != classes:
        return None, "Insufficient represented target classes in training fold"
    w = weights.astype(float)
    w /= w.sum()
    shape = (x.shape[1], classes)
    start = np.zeros(shape) if initial is None else np.asarray(initial).reshape(shape)
    def objective(flat):
        coef = flat.reshape(shape)
        logits = x @ coef
        norm = logsumexp(logits, axis=1)
        probabilities = np.exp(logits - norm[:, None])
        loss = np.dot(w, norm - logits[np.arange(len(y)), y])
        penalty_coef = coef.copy()
        penalty_coef[0] = 0.
        loss += .5 * penalty * np.sum(penalty_coef ** 2)
        probabilities[np.arange(len(y)), y] -= 1
        gradient = x.T @ (probabilities * w[:, None]) + penalty * penalty_coef
        return float(loss), np.asarray(gradient).ravel()
    fit = minimize(objective, start.ravel(), jac=True, method="L-BFGS-B",
                   options={"maxiter": maxiter, "ftol": 1e-7, "gtol": 1e-4,
                            "maxls": 25})
    if not fit.success or not np.isfinite(fit.fun):
        return None, "Fixed-budget multinomial fit did not converge: " + str(fit.message)
    return fit.x.reshape(shape), None


def _model_probability(x, coef):
    from scipy.special import softmax
    return softmax(x @ coef, axis=1)


def _model_series_layout(rows):
    ids = sorted({str(r["series_id"]) for r in rows})
    lookup = {sid: i for i, sid in enumerate(ids)}
    indices = np.asarray([lookup[str(r["series_id"])] for r in rows], int)
    team_counts = {}
    for row in rows:
        key = (str(row["series_id"]), str(row["roster_id"]))
        team_counts[key] = team_counts.get(key, 0) + 1
    teams_per_series = {sid: len({str(r["roster_id"]) for r in rows if str(r["series_id"]) == sid})
                        for sid in ids}
    weights = np.asarray([1. / team_counts[(str(r["series_id"]), str(r["roster_id"]))] /
                           teams_per_series[str(r["series_id"])] for r in rows])
    return ids, indices, weights


def _model_fold_labels(series_ids, indices, seed):
    import hashlib
    order = sorted(range(len(series_ids)), key=lambda j: hashlib.sha256(
        f"model-fold:{seed}:{series_ids[j]}".encode()).digest())
    nfolds = min(5, len(series_ids))
    if nfolds < 3:
        return None, nfolds
    folded = np.empty(len(series_ids), int)
    for j, index in enumerate(order):
        folded[index] = j % nfolds
    return folded[indices], nfolds


def _model_support(train, val, tx, vx, train_weights, idea):
    active = train_weights > 0
    if not active.any():
        return np.zeros(len(val), bool)
    lower, upper = tx["support"][active].min(axis=0), tx["support"][active].max(axis=0)
    tolerance = 1e-8
    keep = np.all((vx["support"] >= lower - tolerance) &
                  (vx["support"] <= upper + tolerance), axis=1)
    regions = {r["region"] for r, ok in zip(train, active) if ok}
    strata = {r["stratum"] for r, ok in zip(train, active) if ok}
    keep &= np.asarray([r["region"] in regions and r["stratum"] in strata for r in val])
    if idea == "B04":
        # Paired input proximity matching uses no responses or validation-derived
        # cutoffs. Both histories remain equal dimension/count/model budget.
        for i, row in enumerate(val):
            td, od = np.sort(row["teammate_distances"]), np.sort(row["opponent_distances"])
            ts, os = np.sort(row["teammate_speeds"]), np.sort(row["opponent_speeds"])
            keep[i] &= np.max(np.abs(td - od)) <= 500. and np.max(np.abs(ts - os)) <= 400.
    return keep


def _model_crossfit(x, y, weights, fold, classes, initial_folds=None):
    probability = np.full((len(y), classes), np.nan)
    coefs = []
    for k in range(int(fold.max()) + 1):
        train_weight = weights * (fold != k)
        initial = initial_folds[k] if initial_folds is not None else None
        coef, error = _model_fit(x, y, train_weight, classes, initial=initial)
        if error:
            return None, None, error
        probability[fold == k] = _model_probability(x[fold == k], coef)
        coefs.append(coef)
    return probability, coefs, None


def _model_calibrator(probability, y, weights, initial=None):
    p = np.clip(probability[:, 1], 1e-6, 1 - 1e-6)
    # Symmetric-class multinomial parameterization preserves L/R reflection.
    # Platt slope/intercept use only out-of-fold training probabilities.
    x = np.column_stack((np.ones(len(p)), np.log(p / (1 - p))))
    coef, error = _model_fit(x, y, weights, 2, initial=initial, penalty=.0001)
    return (x, coef, error)


def _model_apply_calibrator(raw, coef):
    p = np.clip(raw[:, 1], 1e-6, 1 - 1e-6)
    x = np.column_stack((np.ones(len(p)), np.log(p / (1 - p))))
    return _model_probability(x, coef)[:, 1]


def _model_calibration_audit(probabilities, observed, rows, minimum=30):
    p, y = np.asarray(probabilities).ravel(), np.asarray(observed).ravel()
    bins = np.array([0., .2, .4, .6, .8, 1.000001])
    assignments = np.clip(np.digitize(p, bins) - 1, 0, 4)
    report = []
    errors = []
    for k in range(5):
        mask = assignments == k
        n = int(mask.sum())
        if not n:
            continue
        error = abs(float(y[mask].mean() - p[mask].mean()))
        if n >= minimum:
            errors.append(error)
        report.append({"bin": [float(bins[k]), min(1., float(bins[k + 1]))],
                       "n_player_events": n, "mean_predicted": float(p[mask].mean()),
                       "mean_observed": float(y[mask].mean()), "absolute_error": error,
                       "adequate_support": n >= minimum})
    return {"bins": report, "max_supported_absolute_error": max(errors) if errors else None,
            "all_occupied_bins_supported": bool(report) and all(r["adequate_support"] for r in report),
            "passes_003": bool(errors) and all(r["adequate_support"] for r in report) and max(errors) <= .03,
            "note": "Player-event bins are calibration summaries; all inferential resampling is by series."}


def _model_aggregate_layout(rows, all_ids):
    key = (id(rows), tuple(all_ids))
    cached = _MODEL_AGGREGATE_CACHE.get(key)
    if cached is not None and cached[0] is rows:
        return cached[1]
    series_lookup = {sid: i for i, sid in enumerate(all_ids)}
    teams = sorted({(str(row["series_id"]), str(row["roster_id"])) for row in rows})
    team_lookup = {team: j for j, team in enumerate(teams)}
    row_to_team = np.asarray([team_lookup[(str(row["series_id"]), str(row["roster_id"]))]
                              for row in rows], int)
    team_to_series = np.asarray([series_lookup[sid] for sid, _ in teams], int)
    layout = (row_to_team, team_to_series, len(teams), len(all_ids))
    _MODEL_AGGREGATE_CACHE[key] = (rows, layout)
    return layout


def _model_aggregate(rows, components, keep, all_ids):
    """Equal team-series then series means; recompute mask-dependent counts."""
    row_to_team, team_to_series, nteams, nseries = _model_aggregate_layout(rows, all_ids)
    components = np.asarray(components, float)
    keep = np.asarray(keep, bool)
    if components.ndim != 2 or len(components) != len(rows) or len(keep) != len(rows):
        raise ValueError("Aggregate inputs must align")
    selected = row_to_team[keep]
    team_counts = np.bincount(selected, minlength=nteams)
    team_present = team_counts > 0
    series_counts = np.bincount(team_to_series[team_present], minlength=nseries)
    out = np.full((nseries, components.shape[1]), np.nan)
    for column in range(components.shape[1]):
        team_sum = np.bincount(selected, weights=components[keep, column], minlength=nteams)
        team_mean = np.divide(team_sum, team_counts, out=np.zeros(nteams), where=team_present)
        series_sum = np.bincount(team_to_series[team_present],
                                 weights=team_mean[team_present], minlength=nseries)
        np.divide(series_sum, series_counts, out=out[:, column], where=series_counts > 0)
    return out


def _model_statistic(aggregate, multiplicities, idea):
    keep = np.isfinite(aggregate).all(axis=1) & (multiplicities > 0)
    if np.count_nonzero(keep) < 2:
        return np.nan
    means = np.average(aggregate[keep], axis=0, weights=multiplicities[keep])
    if idea == "B04":
        return float(means[0])
    return float(np.log(means[0] / means[1])) if np.min(means) > 0 else np.nan


def _model_components(tx, vx, train_weights, idea, fold, initial=None):
    """Refit every nuisance entering the primary statistic, using train only."""
    if idea == "B04":
        models, probabilities = {}, {}
        for kind in ("own", "opponent"):
            coef, error = _model_fit(tx[kind], tx["y"], train_weights, 3,
                                    initial=None if initial is None else initial["models"][kind])
            if error:
                return None, None, error
            models[kind] = coef
            probabilities[kind] = _model_probability(vx[kind], coef)
        labels = vx["y"]
        own_loss = -np.log(np.clip(probabilities["own"][np.arange(len(labels)), labels], 1e-12, 1))
        other_loss = -np.log(np.clip(probabilities["opponent"][np.arange(len(labels)), labels], 1e-12, 1))
        components = ((other_loss - own_loss) / np.log(2))[:, None]
        return components, {"models": models, "probabilities": probabilities}, None
    probabilities, models, calibrators, fold_models, oof = [], [], [], [], []
    for player in range(3):
        target = tx["y"][:, player]
        raw_oof, fitted_folds, error = _model_crossfit(
            tx["base"], target, train_weights, fold, 2,
            initial_folds=None if initial is None else initial["fold_models"][player])
        if error:
            return None, None, error
        _, calibration, error = _model_calibrator(
            raw_oof, target, train_weights,
            initial=None if initial is None else initial["calibrators"][player])
        if error:
            return None, None, error
        coef, error = _model_fit(tx["base"], target, train_weights, 2,
                                initial=None if initial is None else initial["models"][player])
        if error:
            return None, None, error
        predicted = _model_apply_calibrator(_model_probability(vx["base"], coef), calibration)
        probabilities.append(predicted)
        models.append(coef)
        calibrators.append(calibration)
        fold_models.append(fitted_folds)
        oof.append(_model_apply_calibrator(raw_oof, calibration))
    predicted = np.column_stack(probabilities)
    observed = vx["y"]
    observed_pairs = sum(observed[:, i] * observed[:, j] for i, j in ((0, 1), (0, 2), (1, 2)))
    expected_pairs = sum(predicted[:, i] * predicted[:, j] for i, j in ((0, 1), (0, 2), (1, 2)))
    return np.column_stack((observed_pairs, expected_pairs)), {
        "models": models, "calibrators": calibrators, "fold_models": fold_models,
        "probabilities": predicted, "oof": np.column_stack(oof)}, None


def _model_matched_shuffle(train, tx, weights, seed):
    """Re-pair complete added-history blocks across context-matched train series."""
    from scipy import sparse
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    support = tx["support"]
    current_and_history = tx["base"][:, 1:1 + tx["numeric_columns"]].toarray()
    tree = cKDTree(support)
    _, candidates = tree.query(support, k=min(32, len(train)))
    if candidates.ndim == 1:
        candidates = candidates[:, None]
    donor = np.full(len(train), -1, int)
    for i, near in enumerate(candidates):
        good = [int(j) for j in near if j != i and train[j]["series_id"] != train[i]["series_id"]
                and train[j]["region"] == train[i]["region"]
                and train[j]["season"] == train[i]["season"]
                and train[j]["roster_id"] == train[i]["roster_id"]
                and train[j]["opponent_roster_id"] == train[i]["opponent_roster_id"]
                and train[j]["stratum"] == train[i]["stratum"]
                and np.sqrt(np.mean((support[j] - support[i]) ** 2)) <= .35
                and np.max(np.abs(support[j] - support[i])) <= 1.
                and np.sqrt(np.mean((current_and_history[j] - current_and_history[i]) ** 2)) <= .35
                and np.max(np.abs(current_and_history[j] - current_and_history[i])) <= 1.]
        if good:
            donor[i] = rng.choice(good)
    eligible = donor >= 0
    if np.count_nonzero(eligible) < 30 or len({train[i]["series_id"] for i in np.flatnonzero(eligible)}) < 3:
        return None, {"status": "not_computable", "reason": "Insufficient exchangeable training history blocks",
                      "matched_train_windows": int(eligible.sum())}
    replacement = np.where(eligible, donor, np.arange(len(train)))
    common_size = tx["base"].shape[1]
    null_tx = dict(tx)
    for kind in ("own", "opponent"):
        null_tx[kind] = sparse.hstack((tx["base"], tx[kind][replacement, common_size:]), format="csr")
    return (null_tx, weights * eligible), {
        "status": "computed", "matched_train_windows": int(eligible.sum()),
        "complete_block_reassignment": True, "different_series": True,
        "identity_fallback": "Same focal and opponent roster, season/region/phase; no unverified strength",
        "control_only": True, "no_additional_significance_claim": True}


def prediction_screen(train, val, idea, seed=42, reps=2000, workers=1, progress=None):
    """B04 held-out bits/action or B08 log pair-shortage ratio; train refit bootstrap.

    Three-to-five deterministic whole-series folds. No validation fitting,
    calibration or hyperparameter selection. Exact roster/opponent one-hot
    effects have ridge shrinkage; unseen levels receive the fitted global
    hierarchical mean, with coverage reported rather than silently excluded.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    started = time.perf_counter()
    if idea not in ("B04", "B08"):
        raise ValueError("prediction_screen supports B04 and B08")
    if any(r.get("split") != "train" for r in train):
        raise ValueError("Training-only nuisance fitting required")
    if any(r.get("split") != "val" or r.get("season") != "rlcs-2025" for r in val):
        raise ValueError("Only 2025 validation test statistics are permitted")
    def valid(row):
        if not all(row.get(k) is not None for k in ("series_id", "roster_id", "opponent_roster_id", "region")):
            return False
        try:
            numeric = _model_numeric(row, idea, 1.)
            return all(np.isfinite(np.asarray(part)).all() for part in numeric)
        except (KeyError, TypeError, ValueError, IndexError):
            return False
    original_train, original_val = len(train), len(val)
    train, val = [r for r in train if valid(r)], [r for r in val if valid(r)]
    proximity_lost_train = 0
    if idea == "B04":
        before = len(train)
        train = [r for r in train if
                 np.max(np.abs(np.sort(r["teammate_distances"]) -
                               np.sort(r["opponent_distances"]))) <= 500.
                 and np.max(np.abs(np.sort(r["teammate_speeds"]) -
                                   np.sort(r["opponent_speeds"]))) <= 400.]
        proximity_lost_train = before - len(train)
    audit = {"method": "Fixed-penalty regularized multinomial likelihood",
             "penalty": .1, "max_iterations_per_fit": 75,
             "hyperparameter_candidates": 1, "workers": workers,
             "n_train_rows": len(train), "n_val_rows": len(val),
             "excluded_invalid_train_rows": original_train - len(train),
             "excluded_invalid_val_rows": original_val - len(val),
             "proximity_excluded_train_rows": proximity_lost_train,
             "proximity_rule": "Per-window sorted two-history distances within500uu and speeds within400uu/s"}
    if not train or not val:
        return _model_missing("No finite train/validation rows with verified region and roster context", audit)
    tids, ti, tw = _model_series_layout(train)
    vids, vi, vw = _model_series_layout(val)
    fold, nfolds = _model_fold_labels(tids, ti, seed)
    audit.update(n_train_series=len(tids), n_val_series=len(vids), crossfit_folds=nfolds)
    if fold is None or len(vids) < 2:
        return _model_missing("Need at least three training series and two validation series", audit)
    boost_scale, boost_audit = _model_boost_scale(train, require_saturation=idea == "B08")
    audit["boost_scale"] = boost_audit
    if boost_scale is None:
        return _model_missing("Training boost range has no credible repeated saturation", audit)
    tx, vx, vocabulary = _model_prepare(train, val, idea, boost_scale)
    if tx["own"].shape[1] != tx["opponent"].shape[1]:
        raise ValueError("B04 augmented models must have identical feature dimensions")
    audit["feature_dimensions"] = {k: int(tx[k].shape[1]) for k in ("base", "own", "opponent")}
    audit["categorical_levels"] = len(vocabulary)
    known_rosters = {str(r[k]) for r in train for k in ("roster_id", "opponent_roster_id")}
    audit["validation_both_rosters_seen_fraction"] = float(np.mean([
        str(r["roster_id"]) in known_rosters and str(r["opponent_roster_id"]) in known_rosters for r in val]))
    audit["roster_adjustment"] = "L2-shrunk focal/opponent roster effects; unseen levels shrink to global mean"
    support = _model_support(train, val, tx, vx, tw, idea)
    audit["numeric_and_proximity_supported_val_rows"] = int(support.sum())
    audit["supported_val_series"] = len({str(val[i]["series_id"]) for i in np.flatnonzero(support)})
    audit["supported_unique_replay_anchor_windows"] = len({
        (str(val[i]["replay_id"]), val[i].get("index", val[i].get("time")), val[i].get("focal_team"))
        for i in np.flatnonzero(support)})
    audit["support_loss_fraction"] = float(1 - support.mean())
    if support.sum() < 20 or len({str(val[i]["series_id"]) for i in np.flatnonzero(support)}) < 2:
        return _model_missing("Insufficient shared numeric/proximity support in validation", audit)
    if idea == "B04":
        oof_loss = {}
        for kind in ("base", "own", "opponent"):
            oof, _, error = _model_crossfit(tx[kind], tx["y"], tw, fold, 3)
            if error:
                audit["time_fit_seconds"] = time.perf_counter() - started
                return _model_missing(error, audit)
            loss = -np.log(np.clip(oof[np.arange(len(train)), tx["y"]], 1e-12, 1))
            oof_loss[kind] = float(np.average(loss, weights=tw))
        audit["training_oof_logloss"] = oof_loss
    components, fitted, error = _model_components(tx, vx, tw, idea, fold)
    audit["time_fit_seconds"] = time.perf_counter() - started
    if error:
        return _model_missing(error, audit)
    aggregate = _model_aggregate(val, components, support, vids)
    effect = _model_statistic(aggregate, np.ones(len(vids)), idea)
    retained_series = np.isfinite(aggregate).all(axis=1)
    if not np.isfinite(effect):
        return _model_missing("Degenerate primary estimand (zero observed/expected pairs or too few series)", audit)
    if idea == "B08":
        calibration = _model_calibration_audit(fitted["probabilities"][support], vx["y"][support],
                                              [r for r, k in zip(val, support) if k])
        audit["heldout_marginal_calibration"] = calibration
        audit["training_oof_marginal_calibration"] = _model_calibration_audit(
            fitted["oof"], tx["y"], train)
        means = np.mean(aggregate[retained_series], axis=0)
        audit.update(pair_ratio=float(np.exp(effect)), observed_pair_events=float(components[support, 0].sum()),
                     expected_pair_events=float(components[support, 1].sum()),
                     absolute_pair_shortage_difference=float((means[0] - means[1]) / 3))
        if not calibration["passes_003"]:
            audit["unvalidated_model_effect"] = effect
            return _model_missing("Held-out marginal calibration/support fails the prespecified .03 gate; "
                                  "conditional-independent null is not established", audit)
    else:
        null_train, null_audit = _model_matched_shuffle(train, tx, tw, seed + 111)
        if null_train is not None:
            null_x, null_weights = null_train
            null_components, _, null_error = _model_components(null_x, vx, null_weights, idea, fold)
            if null_error:
                null_audit.update(status="not_computable", reason=null_error)
            else:
                null_aggregate = _model_aggregate(val, null_components, support, vids)
                null_audit["bits_per_action"] = _model_statistic(null_aggregate, np.ones(len(vids)), idea)
        audit["matched_history_shuffle_control"] = null_audit
        # Reflection changes signs of x/vx and swaps L/R classes. L2 penalties
        # and feature dimensions are invariant; actually refit once to verify.
        rtx, rvx, _ = _model_prepare(train, val, idea, boost_scale, reflect=True)
        reflected, _, reflected_error = _model_components(rtx, rvx, tw, idea, fold)
        audit["reflection_effect"] = (None if reflected_error else _model_statistic(
            _model_aggregate(val, reflected, support, vids), np.ones(len(vids)), idea))
        audit["reflection_error"] = reflected_error
        baseline_coef, baseline_error = _model_fit(tx["base"], tx["y"], tw, 3)
        if baseline_error is None:
            baseline_p = _model_probability(vx["base"], baseline_coef)
            baseline_loss = -np.log(np.clip(baseline_p[np.arange(len(val)), vx["y"]], 1e-12, 1))
            audit["heldout_baseline_logloss"] = float(np.average(baseline_loss[support], weights=vw[support]))
    # Whole-series metadata for the two dependence sensitivities.
    event_groups, rosters_by_series = {}, []
    roster_names = sorted({str(r[k]) for r in val for k in ("roster_id", "opponent_roster_id")})
    roster_lookup = {name: j for j, name in enumerate(roster_names)}
    for j, sid in enumerate(vids):
        members = [r for r in val if str(r["series_id"]) == sid]
        events = {str(r.get("event")) for r in members}
        if len(events) == 1:
            event_groups.setdefault(next(iter(events)), []).append(j)
        rosters_by_series.append([roster_lookup[x] for x in sorted(
            {str(r[k]) for r in members for k in ("roster_id", "opponent_roster_id")})])
    event_blocks = list(event_groups.values())
    def replicate(rep):
        rng = np.random.default_rng(np.random.SeedSequence([seed, rep, 804]))
        multiplicities = rng.multinomial(len(tids), np.full(len(tids), 1 / len(tids)))
        weights = tw * multiplicities[ti]
        # Range certification is a nuisance as well: refit if sampled maxima differ.
        scale, _ = _model_boost_scale(train, weights, require_saturation=idea == "B08")
        if scale is None:
            return (np.nan, np.nan, np.nan, "bootstrap boost scale unavailable")
        if np.isclose(scale, boost_scale):
            bx, bv = tx, vx
        else:
            bx, bv, _ = _model_prepare(train, val, idea, scale)
        mask = _model_support(train, val, bx, bv, weights, idea)
        values, _, error = _model_components(bx, bv, weights, idea, fold, initial=fitted)
        if error:
            return (np.nan, np.nan, np.nan, error)
        summary = _model_aggregate(val, values, mask, vids)
        sw = rng.multinomial(len(vids), np.full(len(vids), 1 / len(vids)))
        primary = _model_statistic(summary, sw, idea)
        ew = np.zeros(len(vids))
        if len(event_blocks) >= 2:
            for j in rng.integers(0, len(event_blocks), len(event_blocks)):
                ew[event_blocks[j]] += 1
        event = _model_statistic(summary, ew, idea)
        rw = rng.multinomial(len(roster_names), np.full(len(roster_names), 1 / len(roster_names)))
        crossed = sw * np.asarray([np.prod(rw[ix]) for ix in rosters_by_series])
        multiway = _model_statistic(summary, crossed, idea)
        return primary, event, multiway, None
    boot_start = time.perf_counter()
    samples, failures = [], {}
    executor = ThreadPoolExecutor(max_workers=max(1, workers)) if workers > 1 else None
    iterator = executor.map(replicate, range(reps)) if executor else map(replicate, range(reps))
    try:
        for j, sample in enumerate(iterator):
            samples.append(sample[:3])
            if sample[3]:
                failures[sample[3]] = failures.get(sample[3], 0) + 1
            if progress is not None and (j + 1) % 25 == 0:
                progress(idea=idea, bootstrap_completed=j + 1, bootstrap_total=reps)
    finally:
        if executor:
            executor.shutdown()
    draws = np.asarray(samples, float)
    audit.update(time_bootstrap_seconds=time.perf_counter() - boot_start,
                 bootstrap_failure_reasons=failures, bootstrap_replicates=reps,
                 bootstrap_refits_train_nuisance=True,
                 bootstrap_duplicates_remain_in_original_series_fold=True,
                 full_time_seconds=time.perf_counter() - started)
    primary = _scri_interval(effect, draws[:, 0])
    if primary["valid_replicates"] < .95 * reps:
        audit["bootstrap_valid_replicates"] = primary["valid_replicates"]
        return _model_missing("Fewer than 95% of training/validation series bootstrap fits were estimable", audit)
    audit["event_sensitivity"] = _scri_interval(effect, draws[:, 1])
    audit["roster_series_sensitivity"] = _scri_interval(effect, draws[:, 2])
    order = sorted(np.flatnonzero(retained_series), key=lambda j: str(vids[j]))
    audit["half_effects"] = [_model_statistic(aggregate,
        np.asarray([int(j in order[k::2]) for j in range(len(vids))]), idea) for k in (0, 1)]
    audit["series_weighting"] = "Equal series after equal team-series means"
    audit["nuisance_fit_data"] = "Train seasons only, including every bootstrap refit"
    return {"effect": effect, "ci95": primary["ci95"], "p": primary["p"],
            "n_series": int(retained_series.sum()), "n_events": int(support.sum()),
            "details": audit}


# END PREDICTION METHODS

# BEGIN CONDITIONAL NULL METHODS

# Train-only nuisance models and actual complete-block nulls for B05/B15.
# No Bernoulli fake observations or frame/pulse shuffling appear here.

def _nm_missing(reason, train, val, **audit):
    return dict(effect=None, ci95=[None, None], p=None,
                n_events=len(val), n_series=len({r.get('series_id') for r in val}),
                reason=reason, details=dict(n_train_events=len(train),
                    n_val_events=len(val), **audit))


def _nm_partition(rows, split):
    expected = set(TRAIN_SEASONS) if split == 'train' else {VAL_SEASON}
    for r in rows:
        if r.get('split') != split or r.get('season') not in expected:
            raise ValueError('Nuisance fitting uses train seasons only; tests use 2025 val')
    out = []
    for r in rows:
        x = np.asarray(r.get('controls', []), float).reshape(-1)
        if len(x) and np.isfinite(x).all() and all(r.get(k) not in (None, '', 'nan')
                for k in ('series_id', 'roster_id', 'opponent_roster_id', 'region')):
            out.append(r)
    return out


def _nm_weights(rows, multiplicity=None):
    """Equal team-series then series weights; duplicate bootstrap series stay whole."""
    from collections import Counter, defaultdict
    counts = Counter((r['series_id'], r['roster_id']) for r in rows)
    teams = defaultdict(set)
    for sid, roster in counts:
        teams[sid].add(roster)
    out = np.asarray([1./counts[(r['series_id'], r['roster_id'])]/len(teams[r['series_id']])
                      for r in rows], float)
    if multiplicity is not None:
        out *= np.asarray([multiplicity.get(r['series_id'], 0) for r in rows])
    return out


def _nm_mean(rows, values, multiplicity=None):
    w = _nm_weights(rows, multiplicity)
    values = np.asarray(values, float)
    good = np.isfinite(values) & (w > 0)
    return float(np.average(values[good], weights=w[good])) if good.any() else np.nan


def _nm_draw_series(rows, rng):
    ids = sorted({r['series_id'] for r in rows})
    weights = rng.multinomial(len(ids), np.full(len(ids), 1./len(ids)))
    return dict(zip(ids, weights))


def _nm_design(train, val, extra=None):
    """Fixed physical covariates plus ridge-shrunk roster/opponent hierarchy.
    The category vocabulary uses train only; unseen levels shrink to the population
    intercept rather than being assigned fabricated measured strength.
    """
    from scipy.sparse import csr_matrix, hstack
    fields = ('season', 'region', 'event', 'roster_id', 'opponent_roster_id')
    vocab = {field: {v:j for j,v in enumerate(sorted({str(r.get(field)) for r in train}))}
             for field in fields}
    def matrix(rows):
        base = np.asarray([np.r_[1., np.asarray(r['controls'], float),
                                [] if extra is None else extra(r)] for r in rows])
        parts = [csr_matrix(base)]
        for field in fields:
            rr, cc = [], []
            for i, row in enumerate(rows):
                value = str(row.get(field))
                if value in vocab[field]:
                    rr.append(i); cc.append(vocab[field][value])
            parts.append(csr_matrix((np.ones(len(rr)), (rr, cc)),
                                    shape=(len(rows), len(vocab[field]))))
        return hstack(parts, format='csr')
    return matrix(train), matrix(val), {
        'model': 'Fixed ridge logistic; shrinkage hierarchy for roster/opponent/season/region/event',
        'unseen_val_roster_rows': sum(str(r.get('roster_id')) not in vocab['roster_id'] for r in val),
        'unseen_val_opponent_rows': sum(str(r.get('opponent_roster_id')) not in vocab['opponent_roster_id'] for r in val),
        'ridge_penalty': 1., 'vocabulary_fitted_on': 'train only'}


def _nm_logistic(x, y, weights):
    from scipy.optimize import minimize
    from scipy.special import expit
    y, weights = np.asarray(y, float), np.asarray(weights, float)
    active = weights > 0
    if active.sum() < 3 or len(np.unique(y[active])) < 2:
        raise ValueError('Both response classes required in each fitted training fold')
    # Freeze the original design's likelihood scale. Counting only unique
    # active rows would spuriously strengthen ridge after a weighted bootstrap.
    weights = weights * len(y)/weights.sum()
    penalty = np.ones(x.shape[1]); penalty[0] = 0
    def objective(beta):
        z = np.asarray(x @ beta).ravel()
        loss = float(np.dot(weights, np.logaddexp(0, z)-y*z) + .5*np.dot(penalty, beta*beta))
        gradient = np.asarray(x.T @ (weights*(expit(z)-y))).ravel()+penalty*beta
        return loss, gradient
    result = minimize(objective, np.zeros(x.shape[1]), jac=True, method='L-BFGS-B',
                      options={'maxiter':200, 'ftol':1e-9})
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError('Logistic nuisance optimization did not converge')
    return result.x


def _nm_calibrated_fit(x, y, rows, multiplicity=None):
    """Series-cross-fitted training scores fit a train-only Platt calibrator."""
    from scipy.sparse import csr_matrix
    from hashlib import sha256
    ids = sorted({r.get('_nm_original_series_id',r['series_id']) for r in rows},
                 key=lambda sid:sha256(str(sid).encode()).hexdigest())
    if len(ids) < 3:
        raise ValueError('At least three training series required for calibration cross-fitting')
    folds = {sid:j % min(5, len(ids)) for j,sid in enumerate(ids)}
    assignment = np.asarray([folds[r.get('_nm_original_series_id',r['series_id'])] for r in rows])
    weight = _nm_weights(rows, multiplicity)
    oof = np.full(len(rows), np.nan)
    for fold in sorted(set(folds.values())):
        fitting = assignment != fold
        beta = _nm_logistic(x, y, weight*fitting)
        oof[~fitting] = np.asarray(x[~fitting] @ beta).ravel()
    calibrator = _nm_logistic(csr_matrix(np.column_stack((np.ones(len(rows)), oof))), y, weight)
    beta = _nm_logistic(x, y, weight)
    return beta, calibrator


def _nm_predict(model, x):
    from scipy.special import expit
    beta, calibration = model
    return np.clip(expit(calibration[0]+calibration[1]*np.asarray(x @ beta).ravel()), 1e-7, 1-1e-7)


def _nm_loss(y, probability):
    y = np.asarray(y, float)
    return -(y*np.log(probability)+(1-y)*np.log1p(-probability))


def _nm_series_rows(rows, values):
    from collections import defaultdict
    groups = defaultdict(list)
    for row,value in zip(rows, values):
        groups[row['series_id']].append((row,float(value)))
    out = []
    for sid, entries in sorted(groups.items()):
        rr = [x[0] for x in entries]
        events = {str(r.get('event')) for r in rr if r.get('event')}
        out.append(dict(series_id=sid, effect=_nm_mean(rr, [x[1] for x in entries]),
            n_events=len(rr), roster_ids=sorted({r[k] for r in rr for k in ('roster_id','opponent_roster_id')}),
            event=next(iter(events)) if len(events) == 1 else None))
    return out


def _nm_pool_chunks(blocks, keyfn, featurefn):
    """Outcome-blind matched cliques; full permutation GROUP includes identity.
    Each clique contains mutually exchangeable complete bundles from distinct
    original series. Identity is mandatory for a valid primary permutation test.
    """
    import itertools, math
    from collections import defaultdict
    from hashlib import sha256
    groups=defaultdict(list)
    for block in blocks:
        groups[keyfn(block)].append(block)
    pools,missing,assignment_space,assignment_log10= [],0,1,0.
    def compatible(a,b):
        if a.get('source_series_id',a['series_id'])==b.get('source_series_id',b['series_id']):
            return False
        aa,bb=np.asarray(featurefn(a),float),np.asarray(featurefn(b),float)
        if aa.shape!=bb.shape:return False
        delta=aa-bb
        return bool(np.isfinite(delta).all() and np.sqrt(np.mean(delta*delta))<=.15
                    and np.max(np.abs(delta))<=.30)
    for key,group in sorted(groups.items(),key=lambda x:str(x[0])):
        pending=sorted(group,key=lambda b:sha256(str(b['id']).encode()).hexdigest())
        while pending:
            clique=[pending.pop(0)]
            for candidate in list(pending):
                if len(clique)==7:break
                if all(compatible(candidate,member) for member in clique):
                    clique.append(candidate)
                    pending.remove(candidate)
            if len(clique)<2:
                missing+=len(clique);continue
            permutations=[np.asarray(p,int) for p in itertools.permutations(range(len(clique)))]
            pools.append((clique,permutations))
            factor=math.factorial(len(clique))
            assignment_log10+=math.log10(factor)
            if assignment_space is not None:
                assignment_space*=factor
                if assignment_space>10**100:
                    assignment_space=None
    return pools,dict(matched_block_pools=len(pools),unmatched_blocks=missing,
        distinct_assignment_space=assignment_space,log10_assignment_space=assignment_log10,
        summed_admissible_permutations=sum(len(p) for _,p in pools),
        fixed_rms_caliper=.15,fixed_coordinate_caliper=.30,
        exchangeability='Assumed within mutually matched distinct-series complete-bundle cliques',
        pool_sampling='Uniform full symmetric group INCLUDING identity; fixed ID-hash greedy cliques')


def _nm_permute(pools,n,rng,cross_series_only=False):
    mapping=np.arange(n)
    for subset,permutations in pools:
        choices=permutations
        if cross_series_only:
            # For bias correction only; never this restricted set for primary p.
            choices=[p for p in permutations if np.all(p!=np.arange(len(p)))]
        permutation=choices[int(rng.integers(len(choices)))]
        for target,donor in enumerate(permutation):
            mapping[np.asarray(subset[target]['indices'],int)]=np.asarray(subset[donor]['indices'],int)
    return mapping


def _nm_retained(pools):
    return sorted({int(i) for subset,_ in pools for block in subset for i in block['indices']})


def _nm_reindex_pools(pools, retained):
    lookup = {old:new for new,old in enumerate(retained)}
    return [([{**b, 'indices':[lookup[int(i)] for i in b['indices']]} for b in subset], permutations)
            for subset,permutations in pools]


def _nm_randomization_p(observed, null):
    null = np.asarray(null, float)
    null = null[np.isfinite(null)]
    if not len(null) or np.ptp(null)<1e-12:
        return None
    # Center all assignments symmetrically, including the observed assignment.
    center = float(np.mean(np.r_[observed,null]))
    return float((1+np.sum(np.abs(null-center) >= abs(observed-center)))/(1+len(null)))


def _nm_calibration(rows, y, probability):
    bins = np.array([0., .2, .4, .6, .8, 1.])
    out = []
    for j in range(len(bins)-1):
        mask = (probability >= bins[j]) & ((probability < bins[j+1]) if j < 4 else (probability <= bins[j+1]))
        selected = [r for r,m in zip(rows,mask) if m]
        if selected:
            out.append(dict(bounds=bins[j:j+2].tolist(), n_events=len(selected),
                n_series=len({r['series_id'] for r in selected}),
                absolute_error=abs(_nm_mean(selected, np.asarray(y)[mask]-probability[mask]))))
    return out




def _nm_common_support(train, val):
    """Nearest train contexts under fixed physical calipers; no val fit."""
    from scipy.spatial import cKDTree
    from collections import defaultdict
    groups=defaultdict(list)
    for i,r in enumerate(train):
        groups[(r.get('region'),r.get('stratum'),r.get('score_diff'))].append(i)
    trees={}
    for key,indices in groups.items():
        values=np.asarray([train[i]['controls'] for i in indices],float)
        trees[key]=(cKDTree(values),values)
    retained=[]
    for r in val:
        item=trees.get((r.get('region'),r.get('stratum'),r.get('score_diff')))
        if item is None:continue
        tree,values=item
        query=np.asarray(r['controls'],float)
        if values.shape[1]!=len(query):continue
        _,ix=tree.query(query,k=min(8,len(values)))
        delta=values[np.atleast_1d(ix)]-query
        if np.any((np.sqrt(np.mean(delta*delta,axis=1))<=.15)&(np.max(np.abs(delta),axis=1)<=.30)):
            retained.append(r)
    return retained,dict(n_val_before=len(val),n_val_retained=len(retained),
        matching='Fixed train-context calipers, exact region/phase/score; no validation-fitted scales')


def _nm_boot_rows(rows,rng):
    """Resample actual whole series, including all target and reference blocks."""
    from collections import defaultdict
    grouped=defaultdict(list)
    for i,row in enumerate(rows):
        grouped[row['series_id']].append((i,row))
    ids=sorted(grouped)
    selected=rng.choice(ids,len(ids),replace=True)
    out=[]
    for copy,sid in enumerate(selected):
        for index,row in grouped[sid]:
            out.append({**row,'_nm_original_index':index,
                        '_nm_original_series_id':row.get('_nm_original_series_id',sid),
                        'series_id':str(sid)+'#bootstrap:'+str(copy),
                        'replay_id':str(row['replay_id'])+'#bootstrap:'+str(copy)})
    return out


def _nm_approach_pool(rows):
    """One donor mapping for the complete two-perspective, all-game series bundle.
    Every donor is an actual collection of .5s trajectory blocks. Stable-player
    identity and opponent are exact; all retained episode contexts must align.
    """
    from collections import defaultdict
    grouped=defaultdict(list)
    for i,row in enumerate(rows):
        grouped[row['series_id']].append(i)
    blocks=[]
    for sid,indices in grouped.items():
        indices=sorted(indices,key=lambda i:(tuple(rows[i]['selected_player_ids']),
                           str(rows[i]['roster_id']),str(rows[i]['replay_id']),rows[i].get('time',0)))
        rr=[rows[i] for i in indices]
        blocks.append(dict(id=sid,series_id=sid,source_series_id=rr[0].get('_nm_original_series_id',sid),
                           indices=indices,rows=rr))
    def key(b):
        return tuple((r['season'],r['region'],r['roster_id'],r['opponent_roster_id'],
                      r.get('stratum'),r.get('score_diff'),tuple(r['selected_player_ids'])) for r in b['rows'])
    return _nm_pool_chunks(blocks,key,lambda b:np.asarray(
        [np.r_[r['controls'],np.asarray(r['initial_distances'],float)/1500] for r in b['rows']]))


def approach_screen(train, val, seed=42, reps=2000, progress=None):
    """B05: calibrated independent margins, real conditional pseudo-pairs, series CI."""
    train, val = _nm_partition(train, 'train'), _nm_partition(val, 'val')
    def valid(r):
        y=np.asarray(r.get('y', []), float)
        ids=r.get('selected_player_ids')
        return y.shape == (2,) and np.isin(y,[0,1]).all() and isinstance(ids,(list,tuple)) and len(ids)==2 and all(ids)
    train, val = [r for r in train if valid(r)], [r for r in val if valid(r)]
    if len({r['series_id'] for r in train}) < 3 or len({r['series_id'] for r in val}) < 2:
        return _nm_missing('Insufficient independent train/val series for calibrated B05 fit', train, val)
    val, common_support = _nm_common_support(train,val)
    pools, audit = _nm_approach_pool(val)
    audit['train_context_common_support']=common_support
    retained = _nm_retained(pools)
    if len({val[i]['series_id'] for i in retained}) < 2 or not pools:
        return _nm_missing('No exchangeable same-player/same-opponent cross-series response-block pools', train, val,
                           block_support=audit)
    pools = _nm_reindex_pools(pools, retained)
    val = [val[i] for i in retained]
    if len({r['series_id'] for r in val})<20:
        return _nm_missing('Fewer than 20 matched validation series; stop before expensive marginal/null refits',
                           train,val,block_support=audit,inference_loops_entered=False)
    xtrain, xval, model_audit = _nm_design(train, val,
        extra=lambda r:np.asarray(r['initial_distances'], float)/1500)
    ytrain = np.asarray([r['y'] for r in train], float)
    yval = np.asarray([r['y'] for r in val], float)
    try:
        models = [_nm_calibrated_fit(xtrain,ytrain[:,j],train) for j in (0,1)]
    except ValueError as exc:
        return _nm_missing(str(exc), train, val, block_support=audit)
    probability = np.column_stack([_nm_predict(m,xval) for m in models])
    calibration=[_nm_calibration(val,yval[:,j],probability[:,j]) for j in (0,1)]
    calibration_failed=any(not bins or any(b['n_events']<30 or b['n_series']<5 or
                            b['absolute_error']>.05 for b in bins) for bins in calibration)
    if calibration_failed:
        return _nm_missing('Held-val marginal calibration or bin support fails the frozen implementation audit',
                           train,val,block_support=audit,calibration=calibration,
                           calibration_gate='Each occupied fixed risk bin: >=30 events, >=5 series, absolute error <=.05; implementation choice, not brainstorm threshold')
    expected = probability[:,0]*(1-probability[:,1])+probability[:,1]*(1-probability[:,0])
    observed = (yval[:,0] != yval[:,1]).astype(float)
    individual = observed-expected
    effect = _nm_mean(val, individual)
    result = series_inference(_nm_series_rows(val,individual),seed,reps)
    rng = np.random.default_rng(seed)
    null, boot, assignments = [], [], set()
    from hashlib import sha256
    for iteration in range(reps):
        if progress is not None and iteration%25==0:
            progress(idea='B05',bootstrap_completed=iteration,bootstrap_total=reps)
        permutation = _nm_permute(pools,len(val),rng)
        assignments.add(sha256(permutation.tobytes()).hexdigest())
        pseudo = (yval[:,0] != yval[permutation,1]).astype(float)
        null.append(_nm_mean(val,pseudo-expected))
        train_multiplicity, val_multiplicity = _nm_draw_series(train,rng), _nm_draw_series(val,rng)
        try:
            fitted = [_nm_calibrated_fit(xtrain,ytrain[:,j],train,train_multiplicity) for j in (0,1)]
            p = np.column_stack([_nm_predict(m,xval) for m in fitted])
            independent = p[:,0]*(1-p[:,1])+p[:,1]*(1-p[:,0])
            boot.append(_nm_mean(val,observed-independent,val_multiplicity))
        except ValueError:
            continue
    if progress is not None:
        progress(idea='B05',bootstrap_completed=reps,bootstrap_total=reps)
    interval = _scri_interval(effect, boot)
    result.update(effect=effect,ci95=interval['ci95'],p=_nm_randomization_p(effect,null))
    if len(assignments)<2 or result['p'] is None:
        result['p']=None
        result['reason']='Degenerate primary randomization or fewer than two sampled assignments'
    if len(boot) < max(2,int(.9*reps)):
        result['p']=None
        result['reason']='More than 10% nuisance-refit bootstrap replicates invalid'
    result.setdefault('details',{}).update(model_audit)
    result['details'].update(block_support=audit,
        primary_test='Two-sided conditional complete-response pseudo-pair randomization',
        primary_null_replicates=len(null), sampled_distinct_assignments=len(assignments), null_mean=float(np.mean(null)),
        bootstrap_valid_replicates=len(boot), bootstrap_refits='Both marginal models and train-OOF calibrators refit for each whole-train-series draw',
        observed_exactly_one=_nm_mean(val,observed), independent_expected_exactly_one=_nm_mean(val,expected),
        calibration=[_nm_calibration(val,yval[:,j],probability[:,j]) for j in (0,1)],
        null_response_source='Entire series bundles of actual .5s response blocks; same mapping for all games/both perspectives, stable players/opponent exact',
        diagnostics_00=_nm_mean(val,np.all(yval==0,axis=1)),
        diagnostics_11=_nm_mean(val,np.all(yval==1,axis=1)),
        direction='positive', effect_units='probability difference',
        required_sensitivity_completed=False,
        dependency_sensitivity_interpretation='Event/roster sensitivity conditions on fitted nuisance; does not certify full-procedure robustness')
    return result


def _nm_phase_blocks(rows):
    from collections import defaultdict
    groups=defaultdict(list)
    for i,r in enumerate(rows):
        groups[(r['series_id'],r['replay_id'],r.get('focal_team'),r.get('history_block'))].append(i)
    blocks=[]
    for ident, indices in groups.items():
        indices=sorted(indices,key=lambda i:rows[i]['time'])
        rr=[rows[i] for i in indices]
        times=np.asarray([r['time'] for r in rr])
        # Only full continuous observed history blocks are exchangeable.
        if len(rr)<4 or np.any(np.abs(np.diff(times)-.1)>.04):
            continue
        blocks.append(dict(id=ident, series_id=rr[0]['series_id'],
            source_series_id=rr[0].get('_nm_original_series_id',rr[0]['series_id']), indices=indices,
            rows=rr, pattern=tuple(np.round(times-times[0],2))))
    return blocks


def _nm_phase_pool(rows):
    blocks=_nm_phase_blocks(rows)
    def key(b):
        r=b['rows'][0]
        return tuple(r.get(k) for k in ('season','region','opponent_roster_id','stratum','score_diff'))+(
            int(r['own_pulse_count']),int(r['opponent_pulse_count']),b['pattern'])
    def features(b):
        return np.asarray([np.r_[r['controls'],r['own_period']/4,r['opponent_period']/4]
                           for r in b['rows']])
    return _nm_pool_chunks(blocks,key,features)


def _nm_phase_extra(row):
    period=float(row['own_period'])
    return [np.sin(row['own_phase']),np.cos(row['own_phase']),period/4,
            row['own_pulse_count']/20]+(np.asarray(row['own_history'],float)/4).tolist()


def _nm_phase_matrix(base, rows, mapping=None):
    from scipy.sparse import hstack, csr_matrix
    phi=np.asarray([r['opponent_phase'] for r in rows],float)
    if mapping is not None:
        phi=phi[mapping]
    return hstack((base,csr_matrix(np.column_stack((np.sin(phi),np.cos(phi))))),format='csr')


def _nm_modulation(model, design):
    from scipy.special import expit
    beta,calibration=model
    phase=np.asarray(design[:,-2:] @ beta[-2:]).ravel()
    baseline=np.asarray(design @ beta).ravel()-phase
    amplitude=abs(calibration[1])*float(np.linalg.norm(beta[-2:]))
    eta=calibration[0]+calibration[1]*baseline
    return expit(eta+amplitude)-expit(eta-amplitude)






def _nm_phase_valid(row):
    try:
        fields=('own_phase','opponent_phase','own_period','opponent_period',
                'own_pulse_count','opponent_pulse_count')
        values=np.asarray([row[k] for k in fields],float)
        history=np.asarray(row['own_history'],float)
        return bool(row.get('y') in (0,1) and row.get('history_block') is not None
                    and np.isfinite(values).all() and history.shape==(4,)
                    and np.isfinite(history).all() and np.all(history<=1e-6)
                    and float(row['own_period'])>0 and float(row['opponent_period'])>0)
    except (KeyError,TypeError,ValueError):
        return False


def _nm_phase_coverage(rows):
    """Frozen whole-cycle coverage check: never extrapolate unseen phase extrema."""
    phase=np.mod(np.asarray([r['opponent_phase'] for r in rows],float),2*np.pi)
    labels=np.floor(phase/(2*np.pi)*8).astype(int)
    bins=[]
    for j in range(8):
        selected=[r for r,label in zip(rows,labels) if label==j]
        bins.append(dict(phase_bin=j,n_events=len(selected),
                         n_series=len({r['series_id'] for r in selected})))
    passed=all(b['n_events']>=20 and b['n_series']>=3 for b in bins)
    return dict(passed=passed,bins=bins,
                rule='8 fixed equal phase bins; each >=20 hazard observations and >=3 series')


def phase_screen(train, val, seed=42, reps=2000, progress=None):
    """B15: complete history-block null, joint held-val phase test and DeltaD.
    Eight prespecified independent null fits estimate the modulation bias correction;
    all reps randomizations test the joint phase increment. Bootstrap repeats that
    same eight-null estimator with training refits and whole-series multiplicities.
    """
    train,val=_nm_partition(train,'train'),_nm_partition(val,'val')
    train=[r for r in train if _nm_phase_valid(r)]
    val=[r for r in val if _nm_phase_valid(r)]
    if len({r['series_id'] for r in train})<3 or len({r['series_id'] for r in val})<2:
        return _nm_missing('Insufficient independent series with valid causal cadence histories',train,val)
    val, common_support=_nm_common_support(train,val)
    train_pools,train_audit=_nm_phase_pool(train)
    train_audit['train_context_common_support']=common_support
    val_pools,val_audit=_nm_phase_pool(val)
    ti,vi=_nm_retained(train_pools),_nm_retained(val_pools)
    if len({train[i]['series_id'] for i in ti})<3 or len({val[i]['series_id'] for i in vi})<2:
        return _nm_missing('Insufficient matched complete opponent-history blocks across different series',train,val,
                           train_block_support=train_audit,val_block_support=val_audit)
    train_pools,val_pools=_nm_reindex_pools(train_pools,ti),_nm_reindex_pools(val_pools,vi)
    train,val=[train[i] for i in ti],[val[i] for i in vi]
    if len({r['series_id'] for r in val})<20:
        return _nm_missing('Fewer than 20 matched validation series; stop before expensive phase/null refits',
                           train,val,train_block_support=train_audit,val_block_support=val_audit,
                           inference_loops_entered=False)
    yt,yv=np.asarray([r['y'] for r in train],float),np.asarray([r['y'] for r in val],float)
    if len(np.unique(yt))<2 or len(np.unique(yv))<2:
        return _nm_missing('Pulse and no-pulse hazards are both required in retained train/val support',train,val,
                           train_block_support=train_audit,val_block_support=val_audit)
    phase_coverage={'train':_nm_phase_coverage(train),'val':_nm_phase_coverage(val)}
    if not all(a['passed'] for a in phase_coverage.values()):
        return _nm_missing('Full-cycle opponent-phase support fails frozen coverage audit',
                           train,val,phase_coverage=phase_coverage,inference_loops_entered=False)
    xt,xv,model_audit=_nm_design(train,val,_nm_phase_extra)
    ft,fv=_nm_phase_matrix(xt,train),_nm_phase_matrix(xv,val)
    if np.linalg.matrix_rank(ft[:,-2:].toarray())<2:
        return _nm_missing('Joint sine/cosine phase design is rank deficient',train,val)
    try:
        baseline=_nm_calibrated_fit(xt,yt,train)
        full=_nm_calibrated_fit(ft,yt,train)
    except ValueError as exc:
        return _nm_missing(str(exc),train,val)
    loss0=_nm_loss(yv,_nm_predict(baseline,xv))
    observed_stat=_nm_mean(val,loss0-_nm_loss(yv,_nm_predict(full,fv)))
    observed_mod=_nm_modulation(full,fv)
    rng=np.random.default_rng(seed)
    null_stats,null_mods,assignments=[],[],set()
    from hashlib import sha256
    for iteration in range(reps):
        if progress is not None and iteration%25==0:
            progress(idea='B15',randomization_completed=iteration,randomization_total=reps)
        tmap,vmap=_nm_permute(train_pools,len(train),rng),_nm_permute(val_pools,len(val),rng)
        assignments.add(sha256(tmap.tobytes()+vmap.tobytes()).hexdigest())
        nt,nv=_nm_phase_matrix(xt,train,tmap),_nm_phase_matrix(xv,val,vmap)
        try:
            fitted=_nm_calibrated_fit(nt,yt,train)
            null_stats.append(_nm_mean(val,loss0-_nm_loss(yv,_nm_predict(fitted,nv))))
            null_mods.append(_nm_modulation(fitted,nv))
        except ValueError:
            continue
    if progress is not None:
        progress(idea='B15',randomization_completed=reps,randomization_total=reps)
    correction_fits=min(8,reps)
    if len(null_stats)<max(2,int(.9*reps)):
        return _nm_missing('Insufficient converged complete-procedure history randomizations',train,val,
                           valid_null_replicates=len(null_stats))
    bias_mods=[]
    for _ in range(correction_fits):
        tmap=_nm_permute(train_pools,len(train),rng,cross_series_only=True)
        vmap=_nm_permute(val_pools,len(val),rng,cross_series_only=True)
        nt,nv=_nm_phase_matrix(xt,train,tmap),_nm_phase_matrix(xv,val,vmap)
        try:
            fitted=_nm_calibrated_fit(nt,yt,train)
            bias_mods.append(_nm_modulation(fitted,nv))
        except ValueError:
            continue
    if len(bias_mods)!=correction_fits:
        return _nm_missing('Prespecified cross-series-only null-bias fits did not all converge',train,val)
    null_bias=np.mean(bias_mods,axis=0)
    contribution=observed_mod-null_bias
    effect=_nm_mean(val,contribution)
    result=series_inference(_nm_series_rows(val,contribution),seed,reps)
    boot=[]
    for iteration in range(reps):
        if progress is not None and iteration%25==0:
            progress(idea='B15',bootstrap_completed=iteration,bootstrap_total=reps)
        # Rebuild actual reference pools after whole-series target/reference
        # resampling. Duplicate copies of one original series share a fit fold
        # and can never donate to one another as allegedly independent series.
        bt,bv=_nm_boot_rows(train,rng),_nm_boot_rows(val,rng)
        btp,_=_nm_phase_pool(bt)
        bvp,_=_nm_phase_pool(bv)
        bi,bj=_nm_retained(btp),_nm_retained(bvp)
        if len({bt[i]['_nm_original_series_id'] for i in bi})<3 or len({bv[j]['_nm_original_series_id'] for j in bj})<2:
            continue
        btp,bvp=_nm_reindex_pools(btp,bi),_nm_reindex_pools(bvp,bj)
        bt,bv=[bt[i] for i in bi],[bv[j] for j in bj]
        it=np.asarray([r['_nm_original_index'] for r in bt],int)
        iv=np.asarray([r['_nm_original_index'] for r in bv],int)
        bxt,bxv=xt[it],xv[iv]
        bft,bfv=_nm_phase_matrix(bxt,bt),_nm_phase_matrix(bxv,bv)
        byt=yt[it]
        try:
            refit=_nm_calibrated_fit(bft,byt,bt)
            observed_draw=_nm_modulation(refit,bfv)
            correction=[]
            for _ in range(correction_fits):
                tmap,vmap=_nm_permute(btp,len(bt),rng,cross_series_only=True),_nm_permute(bvp,len(bv),rng,cross_series_only=True)
                nt,nv=_nm_phase_matrix(bxt,bt,tmap),_nm_phase_matrix(bxv,bv,vmap)
                null_fit=_nm_calibrated_fit(nt,byt,bt)
                correction.append(_nm_modulation(null_fit,nv))
            boot.append(_nm_mean(bv,observed_draw-np.mean(correction,axis=0)))
        except ValueError:
            continue
    if progress is not None:
        progress(idea='B15',bootstrap_completed=reps,bootstrap_total=reps)
    interval=_scri_interval(effect,boot)
    result.update(effect=effect,ci95=interval['ci95'],p=_nm_randomization_p(observed_stat,null_stats))
    if len(assignments)<2 or result['p'] is None:
        result['p']=None
        result['reason']='Degenerate joint-phase randomization or fewer than two sampled assignments'
    if len(boot)<max(2,int(.9*reps)):
        result['p']=None
        result['reason']='More than 10% full-procedure nuisance bootstrap refits failed'
    result.setdefault('details',{}).update(model_audit)
    result['details'].update(train_block_support=train_audit,val_block_support=val_audit,
        phase_coverage=phase_coverage,
        observed_modulation=_nm_mean(val,observed_mod),null_modulation=_nm_mean(val,null_bias),
        joint_phase_statistic='Held-val baseline-minus-full Bernoulli log loss for the joint sine/cosine addition',
        joint_phase_statistic_value=observed_stat,
        primary_test='Two-sided centered complete-history randomization of train fits and held-val phase blocks',
        null_replicates=len(null_stats),sampled_distinct_assignments=len(assignments),bootstrap_valid_replicates=len(boot),
        modulation_correction_fits=correction_fits,
        modulation_monte_carlo_se=float(np.std([_nm_mean(val,v) for v in bias_mods],ddof=1)/np.sqrt(correction_fits)) if correction_fits>1 else None,
        bootstrap_refits='Observed and all prespecified null-bias models plus train-OOF calibrators refit',
        bootstrap_reference_method='Actual whole train/val series copied; source pools rebuilt, all null/observed fits and calibration refit; duplicate original series share folds and cannot be cross-series donors',
        n_pulse_events=int(yv.sum()),effect_units='probability modulation per .1s hazard',
        required_dependency_audit=True,
        required_sensitivity_completed=False,
        dependency_sensitivity_interpretation='Event/roster sensitivity conditions on fitted nuisance; does not certify full-procedure robustness')
    return result


# END CONDITIONAL NULL METHODS

def unavailable(reason, summary):
    return {"effect": None, "ci95": [None, None], "p": None,
            "n_series": len(summary["series"]), "n_events": summary["n_events"],
            "reason": reason, "status": "not_computable", "verdict": "not_computable",
            "details": {"n_events_definition": "Measurable candidate windows, NOT identified primary events"}}


def infer_idea(idea, summary, audit, args, progress=None):
    """Apply the exact test or fail closed on an observed required-data failure."""
    if idea in {"B03", "B09", "B12", "B13"}:
        result = unavailable(audit["terminal_reason"] +
            "; complete-horizon-only geometry is not substituted for the goal-aware primary.", summary)
    elif idea in {"B17", "B18"}:
        result = unavailable("Same-season 2025 reference distributions are required; "
                             "all permitted fitting/reference seasons precede 2025.", summary)
    elif idea == "B11":
        result = unavailable("The required 'large ball impulse' exclusion has no numerical "
                             "definition in brainstorm.md; no threshold is invented.", summary)
    elif idea in {"B01", "B04", "B05", "B06", "B08", "B14", "B15"}:
        train = [r for r in summary["rows"] if r["split"] == "train"]
        val = [r for r in summary["rows"] if r["split"] == "val"]
        if idea in {"B01", "B14"}:
            result = gain_screen(train, val, idea, args.seed, args.bootstrap_reps)
        elif idea == "B06":
            result = chirality_screen(train, val, idea, args.seed, args.bootstrap_reps)
        elif idea in {"B04", "B08"}:
            result = prediction_screen(train, val, idea, args.seed, args.bootstrap_reps,
                                       workers=args.workers, progress=progress)
        elif idea == "B05":
            result = approach_screen(train, val, args.seed, args.bootstrap_reps, progress=progress)
        else:
            result = phase_screen(train, val, args.seed, args.bootstrap_reps, progress=progress)

    else:
        rows = summary["rows"]
        train = [r for r in rows if r["split"] == "train"]
        val = [r for r in rows if r["split"] == "val"]
        result = matched_screen(train, val, idea, args.seed, args.bootstrap_reps)
        if result["p"] is None:
            result.update(status="not_computable", verdict="not_computable")
            result.setdefault("reason", "Insufficient nondegenerate independent matched series")
        else:
            result.update(status="estimated")
        detail = result.setdefault("details", {})
        if idea == "B02":
            sensitivity = {}
            for history in ("1.0", "2.0"):
                def relabel(group):
                    output = []
                    for row in group:
                        d = row["history_displacements"][history]
                        if abs(d) > 600:
                            output.append(dict(row, x=1 if d > 0 else -1))
                    return output
                sensitivity[history + "s"] = matched_screen(
                    relabel(train), relabel(val), idea, args.seed+20, args.bootstrap_reps)
            def earlier(group):
                return [dict(r, controls=np.r_[r["controls"], r["earlier_width"]/4096]) for r in group]
            sensitivity["earlier_width"] = matched_screen(
                earlier(train), earlier(val), idea, args.seed+21, args.bootstrap_reps)
            detail["sensitivity"] = sensitivity
            detail["sensitivity_scope"] = "All eligible turning-state anchors; history labels recomputed independently"
        elif idea == "B07":
            def realized(group):
                return [dict(r, controls=np.r_[r["controls"],
                              np.asarray(r["realized_ball_acceleration"])/4600]) for r in group]
            detail["realized_ball_control"] = matched_screen(
                realized(train), realized(val), idea, args.seed+22, args.bootstrap_reps)
        elif idea == "B16":
            detail["raw_30hz_validation"] = "Unavailable: compact-only input"
    detail = result.setdefault("details", {})
    # The protocol requires each contrast side to have >=20 independent series.
    # Tiny-smoke bootstrap tails are not admissible primary p-values.
    if result["n_series"] < 20 and result["p"] is not None:
        detail["insufficient_cluster_bootstrap_p_diagnostic"] = result["p"]
        result["p"] = None
        result["reason"] = "Fewer than 20 independent evaluated series; bootstrap tail is descriptive only"
    result["status"] = "estimated" if result["p"] is not None else "not_computable"
    if result["p"] is None:
        result["verdict"] = "not_computable"
        result.setdefault("reason", "Primary inference lacks adequate support")
    detail["raw_measurement"] = {
        "n_validation_candidates": summary["n_events"],
        "n_candidate_series": len(summary["series"]),
        "mean_raw_x": summary["sum_x"]/summary["nx"] if summary["nx"] else None,
        "mean_raw_y": summary["sum_y"]/summary["ny"] if summary["ny"] else None,
        "warning": "Unadjusted diagnostic values; not the primary effect, CI or null test",
    }
    detail["common_gate_failures"] = [
        "One evaluated season (2025); common G requires >=2, B04 requires >=3",
        audit["series_reason"],
        "Exact event hierarchy not independently certified; full group_path controls are weaker",
    ]
    result.update(id=idea, split="val", n_events=int(result["n_events"]),
                  n_series=int(result["n_series"]))
    return result



def apply_verdicts(results, specs):
    qs = bh18({key:value["p"] for key,value in results.items()})
    thresholds = {"B01":.15, "B02":150., "B04":.02, "B05":.07, "B06":.40,
                  "B07":.05, "B08":float(np.log(.80)), "B10":200., "B14":.15,
                  "B15":.03, "B16":.10}
    minimum_events = {"B01":500,"B02":300,"B04":1000,"B05":500,"B06":200,
                      "B07":400,"B08":200,"B10":300,"B14":300,"B15":500,"B16":200}
    for idea,result in results.items():
        result["q"] = qs[idea]
        result["bh_input_p"] = result["p"] if result["p"] is not None else 1.
        result["screen_criterion"] = specs[idea]["screen_criterion"]
        if result["status"] == "not_computable":
            result["screen_criterion_met"] = False
            continue
        effect,ci,pv = result["effect"],result["ci95"],result["p"]
        direction = -1 if idea == "B08" else 1
        threshold = thresholds[idea]
        directional_ci = ci[1] < 0 if direction < 0 else ci[0] > 0
        basic = (direction*effect >= direction*threshold and pv <= .01
                 and directional_ci and qs[idea] < .1)
        detail = result["details"]
        failures = list(detail["common_gate_failures"])
        if result["n_series"] < 50:
            failures.append("Fewer than 50 independent evaluated series")
        if result["n_events"] < minimum_events[idea]:
            failures.append("Idea-specific minimum event/window count not met")
        halves = detail.get("half_effects", [])
        if idea != "B06" and (len(halves) != 2 or any(x is None or not np.isfinite(x) or direction*x <= 0 for x in halves)):
            failures.append("Prespecified series halves do not both have the predicted sign")
        for key in ("event_sensitivity","roster_series_sensitivity"):
            sensitivity = detail.get(key,{})
            sc = sensitivity.get("ci95",[None,None])
            sp = sensitivity.get("p")
            if basic and (sp is None or sp > .01 or None in sc or
                          (sc[1] >= 0 if direction < 0 else sc[0] <= 0)):
                failures.append(key+" does not support the primary conclusion")
        if idea in {"B01","B06","B14"} and not detail.get("scale_sensitivities_completed",False):
            failures.append("Required gain/chirality scale sensitivities are not completed")
        if idea == "B02":
            if any(v.get("effect") is None or v["effect"] <= 0 for v in detail.get("sensitivity",{}).values()):
                failures.append("History/earlier-width sensitivities do not all retain positive sign")
        elif idea == "B04":
            if detail.get("reflection_effect") is None or detail["reflection_effect"] <= 0:
                failures.append("Reflection sensitivity not positive")
            if detail.get("matched_history_shuffle_control",{}).get("status") != "computed":
                failures.append("Matched complete training-history shuffle control unavailable")
        elif idea == "B05":
            failures.append("100/300 uu gap and realized-ball sensitivities required before scaling")
        elif idea == "B06":
            if detail.get("n_scale_rosters",0) < 10:
                failures.append("Fewer than 10 rosters with >=4 series in each half")
        elif idea == "B07":
            cells = detail.get("cells",{})
            if len(cells) != 4 or any(c["n_events"] < 100 or c["n_series"] < 30 for c in cells.values()):
                failures.append("Four-cell support requirement not met")
            value = detail.get("realized_ball_control",{}).get("effect")
            if value is None or value <= 0:
                failures.append("Realized-ball acceleration sensitivity not positive")
        elif idea == "B08":
            if detail.get("absolute_pair_shortage_difference",0) > -.01:
                failures.append("Absolute pair-shortage reduction below 1 percentage point")
            if min(detail.get("observed_pair_events",0),detail.get("expected_pair_events",0)) < 200:
                failures.append("Observed or expected pair-shortage count below 200")
            if not detail.get("heldout_marginal_calibration",{}).get("passes_003"):
                failures.append("Required marginal calibration gate failed")
        elif idea == "B10":
            pre = detail.get("pretrend_contrast",{}).get("effect")
            frozen = detail.get("frozen_lane_contrast",{}).get("effect")
            if pre is None or abs(pre) >= 100:
                failures.append("Matched pre-period imbalance not below 100 uu")
            if frozen is None or frozen <= 0:
                failures.append("Frozen-lane effect not positive")
        elif idea == "B14":
            if detail.get("observed_gain",float("-inf")) < 1.20:
                failures.append("Raw conditional gain below 1.20")
        elif idea == "B15":
            if detail.get("observed_modulation",0) < .05:
                failures.append("Observed modulation below .05 per .1 s hazard")
            if detail.get("n_pulse_events",0) < 500:
                failures.append("Fewer than 500 pulse events")
            failures.append("Held-out-half direction/phase relationship requires replication")
        elif idea == "B16":
            failures.append("Required raw 30 Hz timing validation unavailable")
        result.update(effect_threshold=threshold,numerical_gate_pass=bool(basic),
                      gate_failures=failures,screen_criterion_met=bool(basic and not failures))
        result["verdict"] = ("promising" if basic and not failures else
            "null" if pv >= .1 and ci[0] <= 0 <= ci[1] and result["n_series"] >= 50 else "weak")
        result["verdict_meaning"] = (
            "Weak includes insufficient support/replication; null means no evidence at this precision, not proof of zero")

def smoke_model_benchmark(totals, seed):
    """One nuisance refit on the SAME six smoke replays; no extra data reads."""
    output = {}
    for idea in ("B04", "B08"):
        rows = totals[idea]["rows"]
        train = [r for r in rows if r["split"] == "train" and r.get("region")]
        val = [r for r in rows if r["split"] == "val" and r.get("region")]
        if idea == "B04":
            def close(r):
                return (np.max(np.abs(np.sort(r["teammate_distances"])-np.sort(r["opponent_distances"]))) <= 500
                        and np.max(np.abs(np.sort(r["teammate_speeds"])-np.sort(r["opponent_speeds"]))) <= 400)
            train, val = list(filter(close, train)), list(filter(close, val))
        if not train or not val:
            output[idea] = {"status":"not_computable", "reason":"No smoke fit rows"}
            continue
        tids, ti, weights = _model_series_layout(train)
        fold, nfolds = _model_fold_labels(tids, ti, seed)
        scale, scale_audit = _model_boost_scale(train, require_saturation=idea == "B08")
        if fold is None or scale is None:
            output[idea] = {"status":"not_computable", "reason":"Insufficient training folds/boost saturation"}
            continue
        tx, vx, _ = _model_prepare(train, val, idea, scale)
        started = time.perf_counter()
        _, _, error = _model_components(tx, vx, weights, idea, fold)
        duration = time.perf_counter()-started
        output[idea] = {"status":"computed" if error is None else "not_computable",
                        "seconds_per_complete_nuisance_refit":duration,
                        "n_train_rows":len(train), "n_val_rows":len(val),
                        "n_train_series":len(tids), "folds":nfolds,
                        "feature_columns":tx["own"].shape[1],
                        "fit_error":error,
                        "scope":"Same bounded smoke sample; runtime benchmark only, no extra observed replay"}
    return output


class Metrics:
    """Private screen run only; never mutates shared idea/dashboard state."""
    def __init__(self, output, name):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not name.startswith("screen-"):
            raise ValueError("Screen run must be a fresh screen-* directory")
        self.directory = Path(output)/"runs"/name
        self.directory.mkdir(parents=True, exist_ok=False)
        self.path = self.directory/"metrics.jsonl"
        self.step = 0

    def emit(self, **values):
        self.step += 1
        row = {"step": self.step, "time": now(), "split": "val",
               "method": "brainstorm_quick_screen", "task": "screen", **values}
        with self.path.open("a") as stream:
            stream.write(json.dumps(clean(row), allow_nan=False)+"\n")
            stream.flush()
        print(json.dumps(clean(row), allow_nan=False), flush=True)


def select_smoke(groups):
    """Three training seasons, three distinct val series; <=6 physical replays."""
    selected = []
    ordered = sorted(groups, key=lambda pair: (
        0 if Path(pair[0]["_shard"]).stem.endswith("0001") else 1,
        int(pair[0]["start"]), pair[0]["replay_id"]))
    for season in TRAIN_SEASONS:
        candidate = next((g for g in ordered if g[0]["season"] == season), None)
        if candidate:
            selected.append(candidate)
    seen = set()
    for group in ordered:
        row = group[0]
        if row["season"] == VAL_SEASON and row["series_id"] not in seen:
            selected.append(group)
            seen.add(row["series_id"])
            if len(seen) == 3:
                break
    if len(selected) > 6:
        raise AssertionError("Smoke cap violated")
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap-reps", type=int, default=2000)
    parser.add_argument("--smoke", action="store_true", help="At most 6 unique replay slices, one worker")
    parser.add_argument("--sanity-check", action="store_true", help="Two shuffled whole-series label controls")
    parser.add_argument("--run", default="screen-"+time.strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args(argv)
    if args.workers < 1 or args.bootstrap_reps < 2:
        parser.error("positive workers and >=2 bootstrap replicates required")
    if args.smoke and args.workers != 1:
        parser.error("Login smoke MUST use --workers 1")
    if not args.smoke and args.bootstrap_reps != 2000:
        parser.error("Prespecified full screen requires exactly 2000 bootstrap replicates")
    if not args.smoke and not os.environ.get("SLURM_JOB_ID"):
        parser.error("Full screen must run in a CPU allocation, never on the login node")
    if args.sanity_check and not args.smoke:
        parser.error("Light sanity check is defined on the smoke sample only")
    started = time.perf_counter()
    log = Metrics(args.output, args.run)
    specs_path = Path(__file__).resolve().parents[2]/"status"/"ideas_brainstorm.json"
    specs = {r["id"]:r for r in json.loads(specs_path.read_text())}
    if set(specs) != set(IDS):
        raise ValueError("Expected exactly the eighteen registered ideas")
    groups, audit = metadata_inventory(args.input)
    if args.smoke:
        groups = select_smoke(groups)
    log.emit(stage="metadata_audit", replays_planned=len(groups),
             val_series_available=audit["val_series"], test_opened=False)
    totals = {idea: {"rows": [], "n_events": 0, "series": set(),
                     "sum_x": 0., "nx": 0, "sum_y": 0., "ny": 0} for idea in IDS}
    boost_audit, completed = [], []
    def accept(item):
        completed.append(item["replay_id"])
        boost_audit.extend(item["boosts"])
        for idea, source in item["ideas"].items():
            target = totals[idea]
            target["rows"].extend(source["rows"])
            target["series"].update(source["series"])
            for key in ("n_events", "sum_x", "nx", "sum_y", "ny"):
                target[key] += source[key]
        if args.smoke or len(completed) % 10 == 0:
            log.emit(stage="measurements", replays_done=len(completed),
                     elapsed_seconds=time.perf_counter()-started)
    extraction_start = time.perf_counter()
    if args.smoke:
        for pair in groups:
            accept(process_replay((pair, args.seed, None)))
    else:
        # One resident decompressed shard on private scratch; jobs are over
        # replays (both perspectives in each job), never statistical units.
        by_shard = defaultdict(list)
        for pair in groups:
            if len({r["_shard"] for r in pair}) != 1:
                raise ValueError("Replay perspectives must share compact shard")
            by_shard[pair[0]["_shard"]].append(pair)
        with tempfile.TemporaryDirectory(prefix="screen-arrays-", dir=args.scratch) as temp:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                for shard, pairs in sorted(by_shard.items()):
                    directory = unpack_shard(Path(shard), Path(temp))
                    tasks = ((pair, args.seed, directory) for pair in pairs)
                    for item in pool.map(process_replay, tasks, chunksize=1):
                        accept(item)
                    shutil.rmtree(directory)
    extraction_seconds = time.perf_counter()-extraction_start
    results = {}
    for idea in IDS:
        log.emit(stage="primary_screen_started", idea=idea)
        results[idea] = infer_idea(idea, totals[idea], audit, args,
            progress=lambda **values: log.emit(stage="inference", **values))
        results[idea]["name"] = specs[idea]["name"]
        results[idea]["metric_spec"] = specs[idea]["metric"]
        results[idea]["null_spec"] = specs[idea]["null"]
        results[idea]["test_spec"] = specs[idea]["test"]
        log.emit(stage="primary_screen", idea=idea, effect=results[idea]["effect"],
                 p=results[idea]["p"], n_series=results[idea]["n_series"],
                 n_events=results[idea]["n_events"])
    apply_verdicts(results, specs)
    sanity = calibration_sanity({k:totals[k]["rows"] for k in ("B02", "B10")}, args.seed) if args.sanity_check else None
    if sanity is not None and any(v["status"] != "passed" for v in sanity.values()):
        raise AssertionError(f"Smoke label control did not pass: {sanity}")
    benchmark = smoke_model_benchmark(totals, args.seed) if args.smoke else None
    elapsed = time.perf_counter()-started
    verdicts = Counter(r["verdict"] for r in results.values())
    payload = {
        "method": "brainstorm_quick_screen", "task": "screen", "split": "val",
        "is_baseline": False, "updated": now(),
        "metrics": {"ideas": len(IDS), "replays_processed": len(completed),
                    "n_train_replays": sum(p[0]["split"] == "train" for p in groups),
                    "n_val_replays": sum(p[0]["split"] == "val" for p in groups),
                    "primary_estimates": sum(r["p"] is not None for r in results.values()),
                    "elapsed_seconds": elapsed,
                    **{k:verdicts[k] for k in ("promising", "weak", "null", "not_computable")}},
        "details": {
            "ideas": results, "audit": audit, "smoke": args.smoke,
            "config": vars(args), "processed_replay_ids": completed,
            "extraction_seconds": extraction_seconds, "smoke_model_benchmark": benchmark,
            "shuffled_label_sanity": sanity, "training_boost_range_audit": boost_audit,
            "family": {"size": 18, "adjustment": "Benjamini-Hochberg",
                       "missing_primary_p": 1., "promising_q_strictly_below": .1},
            "limitations": [
                "Smoke output is an execution check, not a scientific screen of all development replays."
                if args.smoke else "Existing-compact feasibility screen; not unexposed confirmation.",
                "Unavailable controlled tests are not replaced by unadjusted effects.",
                "Validation-only single season cannot meet the literal multi-season scale gate.",
                "Diagnostic summaries are not significance-tested and do not expand the BH family.",
                "Physical matching scales and quality exclusions are frozen implementation choices; "
                "no outcome-selected calipers, no exposure-defining covariates controlled away.",
                "No independently certified complete series membership or terminal-score provenance."
            ]}}
    atomic_json(args.output/"results"/"screen.json", payload)
    atomic_json(log.directory/"summary.json", payload)
    log.emit(stage="complete", elapsed_seconds=elapsed, **dict(verdicts))
    return payload


if __name__ == "__main__":
    main()

