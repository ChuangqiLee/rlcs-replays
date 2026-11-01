"""Generate small synthetic compact shards; never read real replay data.

Each of 12 synthetic players has 20 games in every allowed season. Train and
validation use different exact rosters so the strict RQ4 context control also
has admissible targets. Signals are planted only to exercise the pipeline;
synthetic retrieval scores cannot estimate real-data performance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tactics_code.data import roster_key
from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS, guard_path


def make_fixture(root: Path, *, games_per_player: int = 20,
                 frames: int = 120, seed: int = 314159) -> Path:
    """Write canonical NPZ/parquet fixtures and dangling forbidden sentinels.

    The sentinel links are created without opening their targets. A reader
    which discovers forbidden-season inputs will fail, even before assertions.
    """
    root = guard_path(root)
    if games_per_player < 20 or frames < 100:
        raise ValueError("Fixture must preserve RQ4's 20-game / 10-second gates")
    root.mkdir(parents=True, exist_ok=False)
    (root / "extraction.json").write_text(json.dumps({
        "state_map": {"state_decoding": "per_replay_decoded"},
        "options": {"fps": 10, "synthetic": True, "seed": seed},
        "synthetic_only": True,
    }) + "\n")
    rng = np.random.default_rng(seed)
    ids = [f"synthetic:player-{i:02d}" for i in range(12)]
    train_rosters = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
    val_rosters = [[0, 3, 6], [1, 4, 9], [2, 7, 10], [5, 8, 11]]
    for season in ALLOWED_SEASONS:
        split = "train" if season in TRAIN_SEASONS else "val"
        directory = root / season
        directory.mkdir()
        rosters = train_rosters if split == "train" else val_rosters
        rows, chunks = [], []
        offset = 0
        for fixture in range(2):
            teams = rosters[2 * fixture:2 * fixture + 2]
            for game in range(games_per_player):
                replay = f"synthetic-{season}-fixture{fixture}-game{game:03d}"
                series = f"synthetic-{season}-fixture{fixture}-series{game // 5:03d}"
                time = np.arange(frames, dtype=np.float64) / 10
                global_players = np.zeros((frames, 6, 8), dtype=np.float32)
                for slot, identity_number in enumerate(teams[0] + teams[1]):
                    phase = identity_number * .47
                    frequency = .4 + identity_number * .035
                    global_players[:, slot, 0] = 1700 * np.sin(time * frequency + phase)
                    global_players[:, slot, 1] = 2200 * np.cos(time * frequency + phase)
                    global_players[:, slot, 2] = 30 + 11 * identity_number + 8 * np.sin(time + phase)
                    global_players[:, slot, 3] = 1700 * frequency * np.cos(time * frequency + phase)
                    global_players[:, slot, 4] = -2200 * frequency * np.sin(time * frequency + phase)
                    global_players[:, slot, 5] = 8 * np.cos(time + phase)
                    global_players[:, slot, 6] = 20 + 18 * identity_number
                    global_players[:, slot, :6] += rng.normal(0, 2, (frames, 6))
                global_ball = np.zeros((frames, 6), dtype=np.float32)
                global_ball[:, 0] = 500 * np.sin(time)
                global_ball[:, 1] = 900 * np.cos(time)
                global_ball[:, 2] = 150
                global_ball[:, 3] = 500 * np.cos(time)
                global_ball[:, 4] = -900 * np.sin(time)
                for focal in (0, 1):
                    order = list(range(6)) if focal == 0 else [3, 4, 5, 0, 1, 2]
                    player_numbers = teams[focal] + teams[1 - focal]
                    player_ids = [ids[i] for i in player_numbers]
                    players = global_players[:, order].copy()
                    ball = global_ball.copy()
                    if focal:
                        players[:, :, [0, 1, 3, 4]] *= -1
                        ball[:, [0, 1, 3, 4]] *= -1
                    # Both perspectives contain all six tracks. Only the first
                    # three identities are focal and count as player-games.
                    chunks.append({
                        "players": players,
                        "ball": ball,
                        "time": time.copy(),
                        "frame": np.arange(frames, dtype=np.int64),
                        "live": np.ones(frames, dtype=np.bool_),
                        "segment": np.zeros(frames, dtype=np.int32),
                        "score_diff": np.zeros(frames, dtype=np.int16),
                        "remaining": (300 - time).astype(np.float32),
                        "overtime": np.zeros(frames, dtype=np.bool_),
                        "flags": np.zeros((frames, 6, 4), dtype=np.float32),
                        "roles": np.tile(np.arange(3, dtype=np.int8), (frames, 1)),
                        "role_uncertain": np.zeros(frames, dtype=np.bool_),
                        "touch": np.full(frames, -1, dtype=np.int8),
                    })
                    rows.append({
                        "replay_id": replay, "series_id": series,
                        "season": season, "split": split, "focal_team": focal,
                        "start": offset, "stop": offset + frames, "fps": 10.,
                        "roster_id": roster_key(player_ids[:3]),
                        "opponent_roster_id": roster_key(player_ids[3:]),
                        "player_ids": json.dumps(player_ids),
                        "region": "Europe", "group_path": json.dumps(["synthetic-only"]),
                        "state_decoding": "per_replay_decoded",
                        "state_decoding_details": json.dumps({"failures": []}),
                        "series_membership_complete": True,
                    })
                    offset += frames
        arrays = {key: np.concatenate([c[key] for c in chunks]) for key in chunks[0]}
        np.savez_compressed(directory / "compact-000.npz", **arrays)
        pd.DataFrame(rows).to_parquet(directory / "compact-000.parquet", index=False)
    forbidden = root / "rlcs-2026"
    forbidden.mkdir()
    for suffix in ("npz", "parquet"):
        (forbidden / f"compact-POISON.{suffix}").symlink_to(root / "DO-NOT-OPEN-NONEXISTENT")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(make_fixture(args.root))


if __name__ == "__main__":
    main()
