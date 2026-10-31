#!/usr/bin/env python3
"""Read-only RQ4 game-availability diagnostic; never opens the held-out split.

Run from the project environment: python -B tactics/scripts/rq4_eligibility.py
Only the four explicit season directories and the development-only manifest
are read. No frame parquet, NPZ, raw replay, model, or retrieval is loaded.
"""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import re
import time
import unicodedata

START = time.perf_counter()
import pandas as pd

SEASONS = ("rlcs-21-22", "rlcs-22-23", "rlcs-2024", "rlcs-2025")
LABELS = ("21-22", "22-23", "2024", "2025")
LEVELS = ("roster", "player", "org")
ROOT = Path(__file__).resolve().parents[1]
RUN = "p3-small-41104745-s42-w6-f10-ksweep"


def normalize(value):
    """NFKC, casefold, punctuation/whitespace to single spaces; keep Unicode."""
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in value).split())


def platform_id(player):
    """Match tactics_code.data.stable_player_id exactly."""
    remote = player.get("remote_id")
    if isinstance(remote, dict) and remote:
        parts = [(str(k), str(v)) for k, v in remote.items()
                 if v is not None and str(v) not in ("", "0", "None")]
        return "|".join(f"{k}:{v}" for k, v in sorted(parts)) or None
    return None


def roster_id(ids):
    """Exact three distinct platform IDs, matching the current RQ4 contract."""
    if len(ids) != 3 or any(x is None for x in ids) or len(set(ids)) != 3:
        return None
    return "roster:" + hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest()[:20]


def fixture_names(label, slug=False):
    if slug:
        # Ballchasing group slugs end in a ten-character opaque ID.
        label = re.sub(r"-[a-z0-9]{10}$", "", label)
        label = re.sub(r"^series-\d+-", "", label)
        match = re.fullmatch(r"(.+?)-(?:vs|[0-4]-[0-4])-(.+)", label)
        parts = match.groups() if match else ()
    else:
        parts = re.split(r"\s+vs\.?\s+", label, flags=re.I)
    if len(parts) != 2:
        return ()
    names = tuple(normalize(p) for p in parts)
    return names if all(names) and len(set(names)) == 2 else ()


def org_names(row, manifest):
    # Names are unordered fixture participants, never mapped to focal_team.
    for label in reversed(manifest.get((row.season, row.replay_id), [])):
        names = fixture_names(label)
        if names:
            return names, "manifest"
    # Inspect the stored path string only, not the replay or raw directories.
    if isinstance(row.source_file, str) and "/kaggle/" in row.source_file:
        for label in reversed(Path(row.source_file).parts[:-1]):
            names = fixture_names(label, slug=True)
            if names:
                return names, "source_path"
    return (), "missing"


def table(headers, rows):
    print("| " + " | ".join(map(str, headers)) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print("| " + " | ".join(map(str, row)) + " |")
    print()


def report(scope, entries, coverage):
    print(f"## {scope}\n")
    table(("Season", "Games", "Player platform", "Player name", "Player missing",
           "Roster known", "Roster missing", "Org manifest games",
           "Org path games", "Org missing games"), coverage)
    counts = {}
    for level in LEVELS:
        rows = [(season, unit, len(games))
                for (season, unit), games in entries[level].items()]
        frame = pd.DataFrame(rows, columns=["season", "unit", "games"])
        counts[level] = (frame.pivot(index="unit", columns="season", values="games")
                         .reindex(columns=SEASONS).fillna(0))
    table(("Level", *LABELS, "Distinct units", "Present >=2 seasons"),
          [(level, *[(counts[level][s] > 0).sum() for s in SEASONS],
            len(counts[level]), ((counts[level] > 0).sum(axis=1) >= 2).sum())
           for level in LEVELS])
    rows = []
    for level in LEVELS:
        c = counts[level]
        for threshold in (10, 20, 40):
            good = c >= threshold
            paired = good[list(SEASONS[:3])].mul(good[SEASONS[-1]], axis=0)
            rows.append((level, threshold, *[paired[s].sum() for s in SEASONS[:3]],
                         paired.any(axis=1).sum(), (good.sum(axis=1) >= 2).sum()))
    table(("Level", "Min games/season", "21-22 & 2025", "22-23 & 2025",
           "2024 & 2025", "Any train season & 2025", ">=2 seasons at threshold"), rows)


def main():
    # This existing curated file excludes the held-out records entirely.
    manifest_path = ROOT / "artifacts/rq4-metadata/development_manifest.jsonl"
    manifest_bytes = manifest_path.read_bytes()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if digest != "4b70ad710957f84e2b79e0de6c6ce595d4d4db49f4c5331eb35d2b148d6cb343":
        raise ValueError("Development manifest changed; re-audit its provenance first")
    manifest = {}
    for line in manifest_bytes.splitlines():
        item = json.loads(line)
        assert item["season"] in SEASONS
        key = (item["season"], str(item["id"]))
        path = item.get("group_path", [])
        assert isinstance(path, list)
        if key in manifest and manifest[key] != path:
            raise ValueError(f"Conflicting manifest metadata: {key}")
        manifest[key] = path

    scopes = ("Full source indexes", "Medium run 41104745 compact subset")
    entries = {scope: {level: defaultdict(set) for level in LEVELS} for scope in scopes}
    coverage = {scope: [] for scope in scopes}
    file_count = byte_count = rejected = duplicate_rows = 0
    for season, label in zip(SEASONS, LABELS):
        # Do not glob a shared parent or call read_index()/iter_compact().
        paths = sorted((ROOT.parent / "data/frames/fps30" / season).glob("*.index.parquet"))
        compact_paths = sorted((ROOT / "artifacts" / RUN / "compact" / season)
                               .glob("compact-*.parquet"))
        assert paths and compact_paths, f"Missing metadata for {season}"
        file_count += len(paths) + len(compact_paths)
        byte_count += sum(p.stat().st_size for p in paths + compact_paths)
        df = pd.concat([pd.read_parquet(p, columns=[
            "replay_id", "season", "status", "n_players", "players", "source_file"])
            for p in paths], ignore_index=True)
        compact = pd.concat([pd.read_parquet(p, columns=[
            "replay_id", "season", "split", "focal_team", "roster_id"])
            for p in compact_paths], ignore_index=True)
        assert set(df.season) == {season} and set(compact.season) == {season}
        assert set(compact.split) == {"val" if season == SEASONS[-1] else "train"}
        duplicate_rows += int(df.replay_id.duplicated().sum())
        if df.replay_id.duplicated().any():
            raise ValueError("Duplicate source replay IDs require review")
        assert not compact.duplicated(["replay_id", "focal_team"]).any()
        assert compact.groupby("replay_id").focal_team.apply(set).eq({0, 1}).all()
        compact_ids = set(compact.replay_id)
        compact_rosters = compact.set_index(["replay_id", "focal_team"]).roster_id.to_dict()
        seen_compact = set()
        stats = {scope: Counter() for scope in scopes}
        for row in df.itertuples(index=False):
            if row.status != "ok" or row.n_players != 6:
                rejected += 1
                continue
            players = json.loads(row.players)
            if len(players) != 6 or sorted(p.get("team", -1) for p in players) != [0, 0, 0, 1, 1, 1]:
                rejected += 1
                continue
            platforms = [platform_id(p) for p in players]
            ids = [pid or ("name:" + normalize(p.get("name")) if normalize(p.get("name")) else None)
                   for p, pid in zip(players, platforms)]
            rosters = [roster_id([pid for p, pid in zip(players, platforms) if p["team"] == team])
                       for team in (0, 1)]
            names, source = org_names(row, manifest)
            selected = [scopes[0]]
            if row.replay_id in compact_ids:
                selected.append(scopes[1])
                seen_compact.add(row.replay_id)
                for team, rid in enumerate(rosters):
                    actual = compact_rosters[(row.replay_id, team)]
                    assert (pd.isna(actual) and rid is None) or actual == rid
            for scope in selected:
                stat = stats[scope]
                stat["games"] += 1
                stat["platform"] += sum(p is not None for p in platforms)
                stat["name"] += sum(p is None and i is not None for p, i in zip(platforms, ids))
                stat["player_missing"] += ids.count(None)
                stat["roster_known"] += sum(r is not None for r in rosters)
                stat["roster_missing"] += rosters.count(None)
                stat["org_" + source] += 1
                for level, units in (("player", ids), ("roster", rosters), ("org", names)):
                    for unit in set(units) - {None}:
                        entries[scope][level][(season, unit)].add(row.replay_id)
        assert seen_compact == compact_ids, "Compact games missing valid source metadata"
        for scope in scopes:
            st = stats[scope]
            coverage[scope].append((label, *[st[k] for k in (
                "games", "platform", "name", "player_missing", "roster_known",
                "roster_missing", "org_manifest", "org_source_path", "org_missing")]))
    print("# RQ4 eligibility diagnostic\n")
    print("Allowed seasons: 21-22, 22-23, 2024 (train); 2025 (val).")
    print(f"Run: {RUN}")
    print(f"Read {file_count} index/compact metadata files ({byte_count:,} bytes); "
          f"development manifest {len(manifest_bytes):,} bytes.")
    print(f"Manifest SHA256: {digest}")
    print(f"Rejected source rows (status/player layout): {rejected}; duplicate source IDs: {duplicate_rows}.")
    print("Games = distinct replay IDs per unit per season; train seasons are never pooled.\n")
    for scope in scopes:
        report(scope, entries[scope], coverage[scope])
    elapsed = time.perf_counter() - START
    print(f"Elapsed seconds (including pandas import): {elapsed:.2f}")
    if elapsed >= 300:
        raise RuntimeError("Diagnostic exceeded the five-minute runtime requirement")


if __name__ == "__main__":
    main()
