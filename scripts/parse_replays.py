"""Parse downloaded replays into sharded per-frame Parquet files with subtr-actor.

    python scripts/parse_replays.py [--workers N] [--fps 30] [--shard-size 200] [--limit N]

Inputs:  data/raw/kaggle/<Kaggle season folder>/**.replay   (Kaggle mirror)
         data/raw/ballchasing/<season>/batch-*.tar           (ballchasing downloads, tar shards
                                                              listed in batch-*.ids.json)
         data/raw/ballchasing/<season>/<id>.replay           (loose files from earlier runs)
Outputs: data/frames/fps<F>/<season>/part-<run>-<k>.parquet        frames of ~200 replays
         data/frames/fps<F>/<season>/part-<run>-<k>.index.parquet  one row per replay

Frame shards have one row group per replay and columns `replay_id`, `frame`, the global features
and players p0..p5 (NaN where a game has fewer than 6 players). The index lists every replay of
the shard with its status ("ok" or "failed" plus the error), number of players and frames, the
player order (JSON) and the replay header metadata (JSON).

The home filesystem (GPFS) is very slow when many processes create small files in one directory,
so workers build shards on node-local disk and the main process copies them to GPFS one at a
time. A shard counts as done when its
index file exists; re-running parses only replays not in any index, so it can be re-run as more
downloads arrive. Frame shards without an index (from an interrupted run) are deleted at start.
"""

import argparse
import datetime
import json
import multiprocessing as mp
import os
import pathlib
import re
import shutil
import tarfile
import tempfile
import time
import traceback

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import subtr_actor as sa

PROJECT_DIR = pathlib.Path(__file__).resolve().parent.parent
RAW = PROJECT_DIR / "data" / "raw"
FRAMES = PROJECT_DIR / "data" / "frames"

KAGGLE_SEASON_DIRS = {"RLCS 2021-22": "rlcs-21-22", "RLCS 22-23": "rlcs-22-23", "RLCS 2024": "rlcs-2024"}

GLOBAL_FEATURES = ["BallRigidBody", "CurrentTime", "FrameTime", "SecondsRemaining", "ReplicatedStateName",
                   "BallHasBeenHit"]
PLAYER_FEATURES = ["PlayerRigidBody", "PlayerBoost", "PlayerJump", "PlayerAnyJump", "PlayerDemolishedBy"]
MAX_PLAYERS = 6

HEADERS = sa.get_column_headers(global_feature_adders=GLOBAL_FEATURES, player_feature_adders=PLAYER_FEATURES)
FEATURE_COLUMNS = HEADERS["global_headers"] + [
    f"p{i} - {c}" for i in range(MAX_PLAYERS) for c in HEADERS["player_headers"]]
FRAME_SCHEMA = pa.schema([("replay_id", pa.string()), ("frame", pa.int32())]
                         + [(c, pa.float32()) for c in FEATURE_COLUMNS])
INDEX_SCHEMA = pa.schema([
    ("replay_id", pa.string()), ("season", pa.string()), ("source_file", pa.string()), ("status", pa.string()),
    ("error", pa.string()), ("n_players", pa.int8()), ("n_frames", pa.int32()), ("fps", pa.int16()),
    ("players", pa.string()), ("replay_meta", pa.string()),
])

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def find_replays():
    """Yield (season, replay id, source) for every replay on disk. A source is a path, or
    (tar path, member name) for a replay inside a tar shard."""
    for folder, season in KAGGLE_SEASON_DIRS.items():
        for dirpath, _, files in os.walk(RAW / "kaggle" / folder):
            for name in files:
                if name.endswith(".replay"):
                    m = UUID_RE.search(name)
                    yield season, (m.group(0) if m else pathlib.Path(name).stem), pathlib.Path(dirpath) / name
    bc = RAW / "ballchasing"
    if bc.exists():
        for season_dir in sorted(bc.iterdir()):
            for path in season_dir.glob("*.replay"):
                yield season_dir.name, path.stem, path
            for ids_file in season_dir.glob("*.ids.json"):  # only complete shards have an ids file
                tar_path = ids_file.with_name(ids_file.name.replace(".ids.json", ".tar"))
                for rid in json.loads(ids_file.read_text()):
                    yield season_dir.name, rid, (tar_path, f"{rid}.replay")


def source_name(source):
    if isinstance(source, tuple):
        return f"{source[0].relative_to(PROJECT_DIR)}::{source[1]}"
    return str(source.relative_to(PROJECT_DIR))


def player_order(replay_meta):
    """Players in the order subtr-actor lays out their columns: team 0 then team 1."""
    players = []
    for team_key, team in (("team_zero", 0), ("team_one", 1)):
        for p in replay_meta.get(team_key, []):
            players.append({"team": team, "name": p.get("name"), "remote_id": p.get("remote_id")})
    return players


def parse_replay(season, replay_id, path, source, fps):
    """Return (frame table or None, index row)."""
    row = {"replay_id": replay_id, "season": season, "source_file": source,
           "status": "ok", "error": None, "n_players": None, "n_frames": None, "fps": fps,
           "players": None, "replay_meta": None}
    try:
        meta, arr = sa.get_ndarray_with_info_from_replay_filepath(
            str(path), global_feature_adders=GLOBAL_FEATURES, player_feature_adders=PLAYER_FEATURES,
            fps=fps, dtype="float32")
        n_global, n_per_player = len(HEADERS["global_headers"]), len(HEADERS["player_headers"])
        n_players, rest = divmod(arr.shape[1] - n_global, n_per_player)
        players = player_order(meta["replay_meta"])
        if rest or n_players != len(players) or n_players > MAX_PLAYERS:
            raise ValueError(f"column layout mismatch: {arr.shape[1]} columns for {len(players)} players")
        n = arr.shape[0]
        padded = np.full((n, len(FEATURE_COLUMNS)), np.nan, dtype=np.float32)
        padded[:, :arr.shape[1]] = arr
        arrays = [pa.array([replay_id] * n, pa.string()), pa.array(np.arange(n, dtype=np.int32))]
        arrays += [pa.array(padded[:, j]) for j in range(padded.shape[1])]
        table = pa.Table.from_arrays(arrays, schema=FRAME_SCHEMA)
        row.update(n_players=n_players, n_frames=n,
                   players=json.dumps(players, ensure_ascii=False),
                   replay_meta=json.dumps({k: v for k, v in meta["replay_meta"].items() if k != "all_headers"},
                                          ensure_ascii=False, default=str))
        return table, row
    except Exception as e:
        row.update(status="failed", error=f"{e!r}\n{traceback.format_exc()}"[-4000:])
        return None, row


def build_shard(task):
    """Parse one shard's replays into local temp files (copied to GPFS by the main process)."""
    season, name, jobs, fps, local_dir = task
    local_frames = pathlib.Path(local_dir) / f"{season}-{name}.parquet"
    local_index = pathlib.Path(local_dir) / f"{season}-{name}.index.parquet"
    rows, tars = [], {}
    with pq.ParquetWriter(local_frames, FRAME_SCHEMA, compression="zstd") as writer:
        for replay_id, source in jobs:
            path = source
            if isinstance(source, tuple):  # extract the member from its tar shard to local disk
                tar_path, member = source
                path = pathlib.Path(local_dir) / f"{season}-{name}-{member}"
                try:
                    if tar_path not in tars:
                        tars[tar_path] = tarfile.open(tar_path)
                    with tars[tar_path].extractfile(member) as src, open(path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                except Exception as e:  # unreadable tar or member: record it like a parse failure
                    path.unlink(missing_ok=True)
                    rows.append({"replay_id": replay_id, "season": season, "source_file": source_name(source),
                                 "status": "failed", "error": f"cannot read from tar: {e!r}", "n_players": None,
                                 "n_frames": None, "fps": fps, "players": None, "replay_meta": None})
                    continue
            table, row = parse_replay(season, replay_id, path, source_name(source), fps)
            if isinstance(source, tuple):
                path.unlink()
            if table is not None:
                writer.write_table(table, row_group_size=table.num_rows)  # one row group per replay
            rows.append(row)
    for tar in tars.values():
        tar.close()
    pq.write_table(pa.Table.from_pylist(rows, schema=INDEX_SCHEMA), local_index, compression="zstd")
    ok = sum(r["status"] == "ok" for r in rows)
    return season, name, ok, len(rows) - ok, local_frames, local_index


def publish_shard(season, name, fps, local_frames, local_index):
    """Copy a finished shard to GPFS: frames first, index last (the index is the "done" marker).
    Called from the main process only: concurrent file creation in one GPFS directory stalls."""
    out_dir = FRAMES / f"fps{fps}" / season
    for src, dst in ((local_frames, out_dir / f"{name}.parquet"), (local_index, out_dir / f"{name}.index.parquet")):
        tmp = dst.with_name(dst.name + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
        src.unlink()


def local_scratch():
    for base in (os.environ.get("TMPDIR"), "/local", "/tmp"):
        if base and os.path.isdir(base) and os.access(base, os.W_OK):
            return tempfile.mkdtemp(prefix="rlcs-parse-", dir=base)
    raise RuntimeError("no writable local scratch directory")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", 4)))
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--shard-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=None, help="parse at most N replays (for testing)")
    args = parser.parse_args()

    base = FRAMES / f"fps{args.fps}"
    base.mkdir(parents=True, exist_ok=True)
    done = set()
    for index_file in base.glob("*/*.index.parquet"):
        done.update(pq.read_table(index_file, columns=["replay_id"]).column("replay_id").to_pylist())
    for tmp_file in base.glob("*/*.tmp"):
        tmp_file.unlink()
    for frames_file in base.glob("*/*.parquet"):
        if not frames_file.name.endswith(".index.parquet") and not frames_file.with_name(
                frames_file.name.replace(".parquet", ".index.parquet")).exists():
            print(f"removing incomplete shard {frames_file}", flush=True)
            frames_file.unlink()

    by_season, queued, duplicates = {}, set(), 0
    for season, replay_id, path in find_replays():
        if replay_id in queued:
            duplicates += 1  # a second copy of the same replay (e.g. loose file and tar shard)
            continue
        if replay_id not in done:
            queued.add(replay_id)
            by_season.setdefault(season, []).append((replay_id, path))
    if duplicates:
        print(f"skipped {duplicates} duplicate copies of replays", flush=True)
    n_jobs = sum(len(v) for v in by_season.values())
    if args.limit:
        n_jobs = 0
        for season in list(by_season):
            by_season[season] = by_season[season][:max(0, args.limit - n_jobs)]
            n_jobs += len(by_season[season])

    run = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    local_dir = local_scratch()
    tasks = []
    for season, jobs in sorted(by_season.items()):
        jobs.sort(key=lambda j: source_name(j[1]))  # keep replays of the same event / tar together
        (base / season).mkdir(exist_ok=True)
        for k in range(0, len(jobs), args.shard_size):
            tasks.append((season, f"part-{run}-{k // args.shard_size:04d}", jobs[k:k + args.shard_size],
                          args.fps, local_dir))
    print(f"{n_jobs} replays to parse in {len(tasks)} shards with {args.workers} workers "
          f"(local scratch {local_dir})", flush=True)

    start, ok, failed = time.time(), 0, 0
    try:
        with mp.Pool(args.workers) as pool:
            results = pool.imap_unordered(build_shard, tasks)
            for i, (season, name, n_ok, n_failed, local_frames, local_index) in enumerate(results, 1):
                publish_shard(season, name, args.fps, local_frames, local_index)
                ok, failed = ok + n_ok, failed + n_failed
                print(f"[{i}/{len(tasks)}] {season}/{name}: {n_ok} ok, {n_failed} failed; total {ok} ok, "
                      f"{failed} failed, {(ok + failed) / (time.time() - start):.1f} replays/s", flush=True)
    finally:
        shutil.rmtree(local_dir, ignore_errors=True)
    print(f"finished: {ok} ok, {failed} failed", flush=True)


if __name__ == "__main__":
    main()
