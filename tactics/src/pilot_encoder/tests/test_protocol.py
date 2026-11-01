"""Protocol and leakage checks using only locally generated compact fixtures."""
from __future__ import annotations

import builtins
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from tactics_code.data import iter_compact
from tactics_code.screen import ALLOWED_SEASONS, TRAIN_SEASONS, VAL_SEASON, guard_path
from tactics_code.style_retrieval import (
    check_rows, context_maps, eligible_players, game_features, inventory,
    read_player_slice,
)

from pilot_encoder.dataset import safe_inventory, stage_compact
from .fixture import make_fixture


class CompactProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pilot-protocol-")
        cls.root = make_fixture(Path(cls.temporary.name) / "compact")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_inventory_and_stage_never_open_forbidden_sentinel(self):
        calls = []
        builtin_open, io_open = builtins.open, io.open

        def audited(original):
            def wrapped(file, *args, **kwargs):
                if isinstance(file, (str, bytes, Path)):
                    name = str(file)
                    self.assertNotIn("2026", name)
                    self.assertNotIn("DO-NOT-OPEN", name)
                    calls.append(name)
                return original(file, *args, **kwargs)
            return wrapped

        with tempfile.TemporaryDirectory(prefix="pilot-stage-") as temporary:
            destination = Path(temporary) / "compact"
            with patch("builtins.open", audited(builtin_open)), patch("io.open", audited(io_open)):
                pairs, audit = safe_inventory(self.root)
                staged = stage_compact(self.root, destination)
            self.assertEqual(len(pairs), 160)
            self.assertEqual(staged["replays"], 160)
            self.assertFalse((destination / "rlcs-2026").exists())
            self.assertEqual(audit["read_seasons"], list(ALLOWED_SEASONS))
            self.assertFalse(audit["test_opened"])
            self.assertTrue(calls)

    def test_mislabeled_metadata_is_rejected_before_any_zip_header_open(self):
        # This is synthetic allowed-path metadata only. No forbidden-season
        # file is created or opened; its row labels simulate corrupt input.
        table = pd.read_parquet(self.root / TRAIN_SEASONS[0] / "compact-000.parquet")
        table.loc[0, "season"] = "rlcs-2026"
        table.loc[0, "split"] = "test"
        with tempfile.TemporaryDirectory(prefix="pilot-mislabeled-") as temporary:
            source = Path(temporary) / "compact"
            directory = source / TRAIN_SEASONS[0]
            directory.mkdir(parents=True)
            table.to_parquet(directory / "compact-000.parquet", index=False)
            with patch("zipfile.ZipFile", side_effect=AssertionError("NPZ headers must stay unopened")) as opening:
                with self.assertRaises(ValueError):
                    safe_inventory(source)
                opening.assert_not_called()

    def test_staging_preserves_decode_exclusion_population(self):
        with tempfile.TemporaryDirectory(prefix="pilot-exclusions-") as temporary:
            source = Path(temporary) / "source"
            destination = Path(temporary) / "staged"
            stage_compact(self.root, source)
            metadata_path = source / TRAIN_SEASONS[0] / "compact-000.parquet"
            table = pd.read_parquet(metadata_path)
            replay = table.iloc[0].replay_id
            failures = ["synthetic-exclusion"]
            table.loc[table.replay_id.eq(replay), "state_decoding_details"] = json.dumps({"failures": failures})
            table.to_parquet(metadata_path, index=False)
            exclusion_text = json.dumps({"excluded": {replay: failures}})
            (source / "decode_exclusions.json").write_text(exclusion_text)
            before, _ = safe_inventory(source)
            report = stage_compact(source, destination)
            after, _ = safe_inventory(destination)
            self.assertEqual(len(before), 159)
            self.assertEqual(report["replays"], 159)
            self.assertEqual({pair[0]["replay_id"] for pair in before},
                             {pair[0]["replay_id"] for pair in after})
            self.assertEqual((destination / "decode_exclusions.json").read_text(), exclusion_text)

    def test_paths_and_rows_reject_held_out_split(self):
        with self.assertRaises(ValueError):
            guard_path(self.root / "rlcs-2026" / "compact-POISON.npz")
        with tempfile.TemporaryDirectory(prefix="pilot-link-") as temporary:
            link = Path(temporary) / "alias"
            link.symlink_to(self.root / "rlcs-2026", target_is_directory=True)
            with self.assertRaises(ValueError):
                guard_path(link / "blocked.npz")
        for season, split in (("rlcs-2026", "test"), (VAL_SEASON, "train"), (TRAIN_SEASONS[0], "val")):
            with self.assertRaises(ValueError):
                check_rows(pd.DataFrame([{"season": season, "split": split}]))

    def test_slice_matches_canonical_reader(self):
        pairs, _ = inventory(self.root)
        selected = pairs[0][0]
        meta, arrays = next(iter_compact(selected["_shard"], splits={"train", "val"}))
        self.assertEqual(meta["replay_id"], selected["replay_id"])
        sliced = read_player_slice(selected)
        for key in sliced:
            np.testing.assert_array_equal(sliced[key], arrays[key], err_msg=key)

    def test_fixture_retains_fixed_gate_and_context_population(self):
        pairs, audit = inventory(self.root)
        metadata = [row for pair in pairs for row in pair]
        rows = []
        for shard in sorted(audit["schema"]):
            for meta, arrays in iter_compact(shard, splits={"train", "val"}):
                rows.extend(game_features(meta, arrays))
        games = pd.DataFrame(rows)
        self.assertEqual(len(games), 960)
        self.assertFalse(games.duplicated(["identity_id", "season", "replay_id"]).any())
        train, val = games[games.split == "train"], games[games.split == "val"]
        ids = eligible_players(train, val)
        self.assertEqual(len(ids), 12)
        rosters, teammates = context_maps(metadata)
        for (identity, _), query in val.groupby(["identity_id", "series_id"]):
            query_rosters = set(query.roster_id)
            allowed = [p for p in ids if not rosters[p] & query_rosters and p not in teammates[identity]]
            self.assertIn(identity, allowed)
            self.assertGreaterEqual(len(allowed), 2)

    def test_train_gate_is_not_pooled_across_seasons(self):
        rows = []
        for season in TRAIN_SEASONS:
            for game in range(10):
                rows.append({"identity_id": "one", "season": season,
                             "split": "train", "replay_id": f"{season}-{game}"})
        val = pd.DataFrame([{"identity_id": "one", "season": VAL_SEASON,
                             "split": "val", "replay_id": f"val-{game}"} for game in range(20)])
        train = pd.DataFrame(rows)
        self.assertEqual(eligible_players(train, val), [])
        extra = pd.DataFrame([{"identity_id": "one", "season": TRAIN_SEASONS[0],
                              "split": "train", "replay_id": f"extra-{game}"} for game in range(10)])
        self.assertEqual(eligible_players(pd.concat([train, extra]), val), ["one"])


if __name__ == "__main__":
    unittest.main()
