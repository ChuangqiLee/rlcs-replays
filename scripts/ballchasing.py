"""Crawl the official RLCS group trees on ballchasing.com and download the replay files.

Two long-running commands that can run at the same time (they use different API endpoints,
which ballchasing rate-limits separately):

    python scripts/ballchasing.py crawl      # group tree -> data/manifest/{groups,replays}.jsonl
    python scripts/ballchasing.py download   # manifest -> data/raw/ballchasing/<season>/batch-*.tar
    python scripts/ballchasing.py status     # progress summary

Creating files on the home filesystem (GPFS) can take seconds each, so `download` stages replays
and its rate-limit state on node-local disk (RLCS_STAGE_DIR, default /local/<user>-rlcs-stage) and
packs every ~500 replays into one tar shard on GPFS. A shard's `<name>.ids.json` (written after the
tar) lists its replay ids and marks it complete. Loose data/raw/ballchasing/<season>/<id>.replay
files from earlier runs also count as downloaded.

Both are resumable: re-running picks up where the previous run stopped, and only one instance of
each command can run at a time. Rate limits follow https://ballchasing.com/doc/api and adapt to the
account's Patreon tier, which is re-read from GET /api/ every few minutes (also while waiting for
the hourly budget), so upgrading the tier speeds up a running job.

Exit codes: 0 finished, 2 fatal (bad API key, another instance running), anything else is a crash
that scripts/run_forever.sh restarts.

The API key is read from the environment variable BALLCHASING_API_KEY (or the project's .env).
"""

import argparse
import collections
import fcntl
import getpass
import json
import logging
import os
import pathlib
import re
import shutil
import sys
import tarfile
import time

import requests
from dotenv import load_dotenv

PROJECT_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA = PROJECT_DIR / "data"
MANIFEST = DATA / "manifest"
STATE = DATA / "state"
RAW_BC = DATA / "raw" / "ballchasing"
RAW_KAGGLE = DATA / "raw" / "kaggle"
KAGGLE_DONE = RAW_KAGGLE / ".extract_complete"
LOGS = PROJECT_DIR / "logs"
STAGE = pathlib.Path(os.environ.get("RLCS_STAGE_DIR", f"/local/{getpass.getuser()}-rlcs-stage"))
PACK_EVERY = 500  # staged replays per tar shard

API = "https://ballchasing.com/api"

# Top-level groups created by "RLCS Referee" (steam 76561199225615730), in download priority order.
# RLCS 2021-22 is taken from the Kaggle mirror instead (uploaded by a different account there).
SEASONS = [
    ("rlcs-2026", "rlcs-2026-d3chsz8nje"),
    ("rlcs-2025", "rlcs-2025-7ielfd7uhx"),
    ("rlcs-2024", "rlcs-2024-jsvrszynst"),
    ("rlcs-22-23", "rlcs-22-23-jjc408bdu4"),
]
# Seasons also present in the Kaggle mirror: only replays missing there are downloaded.
KAGGLE_SEASONS = {"rlcs-2024", "rlcs-22-23"}

# (calls per second, calls per hour or None) per endpoint and tier, from the API docs.
_LIST_LIMITS = {"regular": (2, 500), "gold": (2, 1000), "diamond": (4, 2000), "champion": (8, None), "gc": (16, None)}
LIMITS = {
    "groups": _LIST_LIMITS,   # GET /api/groups
    "replays": _LIST_LIMITS,  # GET /api/replays
    "file": {"regular": (1, 200), "gold": (2, 400), "diamond": (2, 1000), "champion": (2, 2000), "gc": (2, None)},
}
HOURLY_SAFETY = 0.95    # stay a little under the hourly caps
SPACING_SAFETY = 1.2    # minimum gap between calls = SPACING_SAFETY / calls-per-second
MAX_KEPT_CALLS = 2500   # more than the largest finite hourly cap
TIER_REFRESH_S = 300
MAX_BACKOFF_S = 900
MAX_ATTEMPTS = 3        # per replay, for errors that may be transient

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

log = logging.getLogger("ballchasing")


class FatalError(Exception):
    """Retrying cannot help (e.g. the API key is rejected)."""


def setup_logging(name):
    LOGS.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOGS / f"{name}.log")):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def single_instance(name, state_dir):
    """Hold an exclusive lock for the life of the process, or exit if another instance has it."""
    state_dir.mkdir(parents=True, exist_ok=True)
    # "a" does not truncate or (after the first run) create anything; lockf locks are enforced by
    # GPFS across nodes, so a second instance on another login node is refused too.
    lock = open(state_dir / f"{name}.lock", "a")
    try:
        fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("another '%s' process is already running", name)
        sys.exit(2)
    return lock


def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def tier_from_type(account_type):
    t = (account_type or "").lower()
    if t == "gc" or "grand" in t:
        return "gc"
    for tier in ("champion", "diamond", "gold"):
        if tier in t:
            return tier
    return "regular"


class RateLimiter:
    """Per-second spacing plus a rolling one-hour window, persisted so restarts don't burst."""

    def __init__(self, endpoint, state_dir):
        self.endpoint = endpoint
        self.path = state_dir / f"ratelimit_{endpoint}.json"
        if not self.path.exists() and (STATE / self.path.name).exists():
            shutil.copyfile(STATE / self.path.name, self.path)  # carry over history kept on GPFS earlier
        self.calls = collections.deque(maxlen=MAX_KEPT_CALLS)
        self.per_second, self.per_hour = LIMITS[endpoint]["regular"]
        if self.path.exists():
            cutoff = time.time() - 3600
            try:
                self.calls.extend(t for t in json.loads(self.path.read_text()) if t > cutoff)
            except (ValueError, OSError):
                # Unreadable state: assume the last write used up the hourly budget.
                mtime = self.path.stat().st_mtime
                log.warning("%s unreadable; assuming the hourly budget was used at its mtime", self.path)
                if mtime > cutoff:
                    self.calls.extend([mtime] * int(self.per_hour * HOURLY_SAFETY))

    def set_tier(self, tier):
        self.per_second, self.per_hour = LIMITS[self.endpoint][tier]

    def wait(self, refresh_tier):
        logged = False
        while True:
            refresh_tier()  # picks up a tier change even during a long hourly wait
            now = time.time()
            while self.calls and self.calls[0] <= now - 3600:
                self.calls.popleft()
            delay = 0.0
            if self.calls:
                delay = self.calls[-1] + SPACING_SAFETY / self.per_second - now
            if self.per_hour is not None and len(self.calls) >= int(self.per_hour * HOURLY_SAFETY):
                delay = max(delay, self.calls[0] + 3600 - now)
                if delay > 5 and not logged:
                    log.info("%s: hourly budget used (%d calls), waiting up to %.0f s", self.endpoint, len(self.calls), delay)
                    logged = True
            if delay <= 0:
                break
            time.sleep(min(delay, 30))
        self.calls.append(time.time())
        write_atomic(self.path, json.dumps(list(self.calls)))
        self.calls[-1] = time.time()  # the moment the request is actually sent


class Client:
    def __init__(self, endpoints, state_dir=STATE):
        load_dotenv(PROJECT_DIR / ".env")
        key = os.environ.get("BALLCHASING_API_KEY")
        if not key:
            raise FatalError("BALLCHASING_API_KEY is not set (put it in .env or the environment)")
        self.session = requests.Session()
        self.session.headers["Authorization"] = key
        state_dir.mkdir(parents=True, exist_ok=True)
        self.limiters = {e: RateLimiter(e, state_dir) for e in endpoints}
        self.tier = None
        self.tier_checked = 0.0
        self.consecutive_429 = 0

    def refresh_tier(self, force=False):
        if not force and time.time() - self.tier_checked < TIER_REFRESH_S:
            return
        self.tier_checked = time.time()
        try:
            r = self.session.get(f"{API}/", timeout=30)
            if r.status_code == 401:
                raise FatalError(f"API key rejected: {r.text[:200]}")
            r.raise_for_status()
            account_type = r.json().get("type")
        except (requests.RequestException, ValueError) as e:
            log.warning("tier check failed (%s); keeping %s limits", e, self.tier or "regular")
            return
        tier = tier_from_type(account_type)
        if tier != self.tier:
            log.info("account type %r -> using %s rate limits %s", account_type, tier,
                     {e: LIMITS[e][tier] for e in self.limiters})
            self.tier = tier
            for limiter in self.limiters.values():
                limiter.set_tier(tier)

    def get(self, endpoint, url, params=None, stream=False):
        """Rate-limited GET. Retries 429, 5xx and network errors indefinitely with backoff;
        raises FatalError on 401 (key rejected); returns any other response for the caller to handle."""
        backoff = 60
        while True:
            self.limiters[endpoint].wait(self.refresh_tier)
            try:
                r = self.session.get(url, params=params, timeout=120, stream=stream)
            except requests.RequestException as e:
                log.warning("network error on %s: %s; retry in %d s", url, e, backoff)
            else:
                if r.status_code == 401:
                    raise FatalError(f"HTTP 401 on {url}: {r.text[:200]}")
                if r.status_code == 429:
                    # The server has sent "Retry-After: 0"; still cool down, longer on each consecutive 429.
                    self.consecutive_429 += 1
                    retry_after = r.headers.get("Retry-After")
                    server_wait = int(retry_after) if retry_after and retry_after.isdigit() else 0
                    wait = max(server_wait, min(10 * 2 ** (self.consecutive_429 - 1), MAX_BACKOFF_S))
                    log.warning("429 on %s (Retry-After %s, %d in a row); cooling down %d s",
                                url, retry_after, self.consecutive_429, wait)
                    r.close()
                    time.sleep(wait)
                    continue
                if r.status_code < 500:
                    self.consecutive_429 = 0
                    return r
                log.warning("HTTP %d on %s; retry in %d s", r.status_code, url, backoff)
                r.close()
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a line being written by the other process, or cut short by a crash
    return rows


def append_jsonl(path, rows):
    if not rows:
        return
    with open(path, "a+") as f:
        # If a crash left a partial last line, start on a fresh line so the new row stays parseable.
        if f.tell() > 0:
            f.seek(f.tell() - 1)
            if f.read(1) != "\n":
                f.write("\n")
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- crawl

def list_all(client, endpoint, params):
    """Follow `next` links of a list endpoint ("groups" or "replays") and yield every item."""
    r = client.get(endpoint, f"{API}/{endpoint}", params=params)
    while True:
        r.raise_for_status()
        page = r.json()
        yield from page.get("list", [])
        nxt = page.get("next")
        if not nxt:
            return
        r = client.get(endpoint, nxt)


def crawl(args):
    """Walk each season's group tree depth-first. A group is recorded in groups.jsonl only after
    its own replays and its child-group list are saved, so a restart redoes at most one group."""
    MANIFEST.mkdir(parents=True, exist_ok=True)
    groups_path, replays_path = MANIFEST / "groups.jsonl", MANIFEST / "replays.jsonl"
    done = {g["id"]: g for g in read_jsonl(groups_path)}
    seen_replays = {r["id"] for r in read_jsonl(replays_path)}
    client = Client(["groups", "replays"])
    client.refresh_tier(force=True)

    for season, root in SEASONS:
        if args.season and season not in args.season:
            continue
        # Stack of (group id, name path, direct replays, indirect replays); the root counts are unknown.
        stack = [(root, [season], None, None)]
        n_groups = n_new = 0
        while stack:
            gid, path, direct, indirect = stack.pop()
            if gid in done:
                rec = done[gid]
                stack.extend((c["id"], path + [c["name"]], c["direct"], c["indirect"]) for c in reversed(rec["children"]))
                continue

            new_rows, children = [], []
            try:
                if direct is None or direct > 0:
                    for item in list_all(client, "replays", {"group": gid, "count": 200}):
                        if item["id"] in seen_replays:
                            continue
                        new_rows.append({
                            "id": item["id"], "season": season, "group": gid, "group_path": path,
                            "title": item.get("replay_title"), "date": item.get("date"),
                            "rocket_league_id": item.get("rocket_league_id"), "duration": item.get("duration"),
                            "playlist": item.get("playlist_id"), "map": item.get("map_code"),
                        })
                # If every replay below this group is a direct replay, there are no replays in sub-groups.
                if indirect is None or direct is None or indirect > direct:
                    for g in list_all(client, "groups", {"group": gid, "count": 200}):
                        children.append({"id": g["id"], "name": g["name"],
                                         "direct": g.get("direct_replays"), "indirect": g.get("indirect_replays")})
            except requests.HTTPError as e:
                # 400/404/410 etc. for one group: record it so restarts don't loop on it.
                code = e.response.status_code
                log.warning("HTTP %d listing group %s (%s); skipping it", code, gid, " / ".join(path))
                append_jsonl(STATE / "crawl_failed_groups.jsonl",
                             [{"id": gid, "season": season, "path": path, "status": code, "time": time.time()}])
                rec = {"id": gid, "season": season, "path": path, "n_replays": 0, "children": [], "error": code}
                append_jsonl(groups_path, [rec])
                done[gid] = rec
                continue

            append_jsonl(replays_path, new_rows)
            seen_replays.update(r["id"] for r in new_rows)
            rec = {"id": gid, "season": season, "path": path, "n_replays": len(new_rows), "children": children}
            append_jsonl(groups_path, [rec])
            done[gid] = rec
            stack.extend((c["id"], path + [c["name"]], c["direct"], c["indirect"]) for c in reversed(children))
            n_groups += 1
            n_new += len(new_rows)
            if n_groups % 50 == 0:
                log.info("%s: %d groups crawled, %d replays listed so far", season, n_groups, n_new)
        log.info("%s: crawl complete (%d new groups, %d new replays this run)", season, n_groups, n_new)
        (STATE / f"crawl_{season}.complete").touch()
    log.info("crawl finished")


# --------------------------------------------------------------------------- download

def kaggle_ids():
    """Ballchasing ids present in the extracted Kaggle mirror (file names are replay ids)."""
    ids = set()
    for dirpath, _, files in os.walk(RAW_KAGGLE):
        for name in files:
            m = UUID_RE.search(name)
            if m and name.endswith(".replay"):
                ids.add(m.group(0))
    return ids


def is_replay(path):
    with open(path, "rb") as f:
        head = f.read(256)
    return b"TAGame.Replay" in head


def downloaded_ids():
    """{replay id: location} for replays already on GPFS: tar shards with an ids file, loose files."""
    have = {}
    if RAW_BC.exists():
        for season_dir in RAW_BC.iterdir():
            for ids_file in season_dir.glob("*.ids.json"):
                for rid in json.loads(ids_file.read_text()):
                    have[rid] = ids_file.name
            for path in season_dir.glob("*.replay"):
                have[path.stem] = path.name
    return have


def pack_staged():
    """Move staged replays to GPFS as one tar shard per season, then delete them locally.
    Returns the replay ids packed."""
    packed = []
    for season_dir in sorted(STAGE.glob("rlcs-*")):
        files = sorted(season_dir.glob("*.replay"))
        if not files:
            continue
        name = f"batch-{time.strftime('%Y%m%d%H%M%S')}-{len(files)}"
        local_tar = STAGE / f"{season_dir.name}-{name}.tar"
        try:
            with tarfile.open(local_tar, "w") as tar:
                for f in files:
                    tar.add(f, arcname=f.name)
            out_dir = RAW_BC / season_dir.name
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f"{name}.tar.tmp"
            shutil.copyfile(local_tar, tmp)
            os.replace(tmp, out_dir / f"{name}.tar")
            ids = [f.stem for f in files]
            write_atomic(out_dir / f"{name}.ids.json", json.dumps(ids))  # marks the shard complete
        finally:
            local_tar.unlink(missing_ok=True)
        for f in files:
            f.unlink()
        packed += ids
        log.info("packed %d replays into %s/%s.tar", len(ids), season_dir.name, name)
    return packed


def download(args):
    local_state = STAGE / "state"
    client = Client(["file"], state_dir=local_state)
    client.refresh_tier(force=True)
    failed_path = STATE / "download_failed.jsonl"
    failed = {r["id"] for r in read_jsonl(failed_path)}
    attempts = collections.Counter()  # transient failures per replay in this run
    seasons = args.season or [s for s, _ in SEASONS]
    need_kaggle = any(s in KAGGLE_SEASONS for s in seasons)
    kaggle = None
    season_rank = {s: i for i, (s, _) in enumerate(SEASONS)}
    n_done = idle_loops = 0

    for part in STAGE.glob("rlcs-*/*.part"):
        part.unlink()
    have = downloaded_ids()
    for f in STAGE.glob("rlcs-*/*.replay"):
        if f.stem in have:
            f.unlink()  # packed by a run killed before it deleted its staged copies
    pack_staged()  # replays staged by an interrupted run
    have = set(downloaded_ids())
    log.info("%d replays already on GPFS; staging in %s", len(have), STAGE)

    def give_up(replay_id, status):
        append_jsonl(failed_path, [{"id": replay_id, "status": status, "time": time.time()}])
        failed.add(replay_id)

    def transient_failure(replay_id, status):
        attempts[replay_id] += 1
        if attempts[replay_id] >= MAX_ATTEMPTS:
            log.warning("%s failed %d times (%s); giving up on it", replay_id, attempts[replay_id], status)
            give_up(replay_id, status)

    while True:
        crawl_complete = all((STATE / f"crawl_{s}.complete").exists() for s in seasons)
        if kaggle is None and KAGGLE_DONE.exists():
            kaggle = kaggle_ids()
            log.info("Kaggle mirror: %d replay ids", len(kaggle))

        todo, held_back = [], 0
        for r in read_jsonl(MANIFEST / "replays.jsonl"):
            if r["season"] not in seasons or r["id"] in failed or r["id"] in have:
                continue
            if r["season"] in KAGGLE_SEASONS:
                if kaggle is None:
                    held_back += 1  # wait until the Kaggle extraction is finished
                    continue
                if r["id"] in kaggle:
                    continue
            todo.append(r)
        todo.sort(key=lambda r: (season_rank[r["season"]], r.get("date") or ""))

        if not todo:
            if crawl_complete and (kaggle is not None or not need_kaggle):
                log.info("download finished (%d files this run, %d failed overall)", n_done, len(failed))
                return
            if idle_loops % 10 == 0:
                log.info("nothing to download yet (crawl complete: %s, Kaggle extraction done: %s, %d replays "
                         "held back until it is)", crawl_complete, kaggle is not None, held_back)
            idle_loops += 1
            time.sleep(60)
            continue
        idle_loops = 0

        log.info("%d replays to download (tier %s)", len(todo), client.tier)
        # Download a batch to local disk, pack it to GPFS, then re-read the manifest.
        for r in todo[:PACK_EVERY]:
            out = STAGE / r["season"] / f"{r['id']}.replay"
            out.parent.mkdir(parents=True, exist_ok=True)
            part = out.with_suffix(".part")
            resp = client.get("file", f"{API}/replays/{r['id']}/file", stream=True)
            if resp.status_code in (403, 404, 410):
                log.warning("HTTP %d for %s; replay is gone or private, skipping it", resp.status_code, r["id"])
                give_up(r["id"], resp.status_code)
                resp.close()
                continue
            if resp.status_code != 200:
                log.warning("HTTP %d for %s", resp.status_code, r["id"])
                transient_failure(r["id"], resp.status_code)
                resp.close()
                continue
            # Content-Length is the compressed size when the body is content-encoded; only compare raw bodies.
            encoded = resp.headers.get("Content-Encoding", "identity").lower() not in ("", "identity")
            expected = None if encoded else resp.headers.get("Content-Length")
            try:
                with open(part, "wb") as f:
                    for chunk in resp.iter_content(1 << 20):
                        f.write(chunk)
            except requests.RequestException as e:
                log.warning("download of %s interrupted (%s)", r["id"], e)
                part.unlink(missing_ok=True)
                transient_failure(r["id"], "interrupted")
                continue
            size = part.stat().st_size
            if (expected and expected.isdigit() and size != int(expected)) or not is_replay(part):
                log.warning("%s: bad body (%d bytes, expected %s)", r["id"], size, expected)
                part.unlink(missing_ok=True)
                transient_failure(r["id"], "bad_body")
                continue
            part.rename(out)
            n_done += 1
            if n_done % 100 == 0:
                log.info("downloaded %d files this run", n_done)
        have.update(pack_staged())


# --------------------------------------------------------------------------- status

def status(args):
    replays = read_jsonl(MANIFEST / "replays.jsonl")
    failed = {r["id"] for r in read_jsonl(STATE / "download_failed.jsonl")}
    kaggle = kaggle_ids() if KAGGLE_DONE.exists() else set()
    have = downloaded_ids()
    staged = {p.stem for p in STAGE.glob("rlcs-*/*.replay")}
    by_season = collections.defaultdict(collections.Counter)
    for r in replays:
        c = by_season[r["season"]]
        c["listed"] += 1
        if r["id"] in have or r["id"] in staged:
            c["downloaded"] += 1
        elif r["season"] in KAGGLE_SEASONS and r["id"] in kaggle:
            c["in_kaggle"] += 1
        elif r["id"] in failed:
            c["failed"] += 1
        else:
            c["remaining"] += 1
    print(f"{'season':12} {'crawl':9} {'listed':>7} {'kaggle':>7} {'downloaded':>10} {'failed':>7} {'remaining':>9}")
    for season, _ in SEASONS:
        c = by_season[season]
        crawl_state = "done" if (STATE / f"crawl_{season}.complete").exists() else "running"
        print(f"{season:12} {crawl_state:9} {c['listed']:7} {c['in_kaggle']:7} {c['downloaded']:10} {c['failed']:7} {c['remaining']:9}")
    print(f"Kaggle extraction: {'done' if KAGGLE_DONE.exists() else 'not finished'} ({len(kaggle)} ids)")
    print(f"staged on local disk, not yet packed to GPFS: {len(staged)} ({STAGE})")
    bad_groups = read_jsonl(STATE / "crawl_failed_groups.jsonl")
    if bad_groups:
        print(f"groups skipped after HTTP errors: {len(bad_groups)} (see data/state/crawl_failed_groups.jsonl)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("crawl", "download", "status"):
        p = sub.add_parser(name)
        p.add_argument("--season", action="append", choices=[s for s, _ in SEASONS],
                       help="limit to these seasons (repeatable); default all")
    args = parser.parse_args()
    if args.cmd == "status":
        status(args)
        return
    setup_logging(args.cmd)
    lock = single_instance(args.cmd, STATE)  # noqa: F841  (held until exit)
    try:
        {"crawl": crawl, "download": download}[args.cmd](args)
    except FatalError as e:
        log.error("fatal: %s", e)
        sys.exit(2)


if __name__ == "__main__":
    main()
