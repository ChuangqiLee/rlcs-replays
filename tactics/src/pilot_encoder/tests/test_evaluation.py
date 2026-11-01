"""Synthetic equivalence checks against the frozen RQ4 retrieval protocol."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from tactics_code.data import iter_compact, parsed_json
from tactics_code.style_retrieval import evaluate_retrieval, game_features, inventory

from pilot_encoder.evaluation import compare_reference, evaluate_embeddings
from .fixture import make_fixture


POPULATION_KEYS = (
    "queries_total", "queries_evaluated", "n_series", "excluded_true_identity",
    "excluded_fewer_than_two_candidates", "candidate_count", "null_stratum_sizes",
)


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pilot-evaluation-")
        cls.root = make_fixture(Path(cls.temporary.name) / "compact")
        pairs, audit = inventory(cls.root)
        cls.metadata = [row for pair in pairs for row in pair]
        rows = []
        for shard in sorted(audit["schema"]):
            for meta, arrays in iter_compact(shard, splits={"train", "val"}):
                rows.extend(game_features(meta, arrays))
        cls.frame = pd.DataFrame(rows)
        cls.identities = sorted(cls.frame.identity_id.unique())
        cls.columns = [f"e_{i:03d}" for i in range(len(cls.identities))]
        cls.frame[cls.columns] = np.eye(len(cls.identities))[
            [cls.identities.index(identity) for identity in cls.frame.identity_id]
        ]
        cls.source = {
            "input_files": [
                {"path": shard, "bytes": Path(shard).stat().st_size,
                 "metadata_sha256": hashlib.sha256(Path(shard).with_suffix(".parquet").read_bytes()).hexdigest()}
                for shard in sorted(audit["schema"])
            ],
            "replay_ids": [pair[0]["replay_id"] for pair in pairs],
            "player_games": len(cls.frame),
            "player_games_by_season": cls.frame.groupby("season").size().to_dict(),
        }

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def evaluate_pair(self, frame=None, metadata=None):
        frame = self.frame if frame is None else frame
        metadata = self.metadata if metadata is None else metadata
        learned = evaluate_embeddings(frame, self.columns, metadata,
                                      permutations=24, bootstrap=24, seed=42)
        frozen = evaluate_retrieval(frame[frame.split == "train"], frame[frame.split == "val"],
                                    self.columns, metadata, permutations=24, bootstrap=24, seed=42)
        return learned, frozen

    def assert_protocol_equal(self, learned, frozen):
        for key in ("eligible_before_region", "excluded_unknown_train_region", "n_gallery", "eligible_ids"):
            self.assertEqual(learned[key], frozen[key], key)
        for analysis in ("primary", "team_context_control"):
            for key in POPULATION_KEYS:
                self.assertEqual(learned[analysis][key], frozen[analysis][key], f"{analysis}.{key}")
            for metric in ("top1", "top5", "mrr"):
                self.assertEqual(learned[analysis]["metrics"][metric], frozen[analysis]["metrics"][metric])

    def test_planted_vectors_have_frozen_protocol_population_and_inference(self):
        learned, frozen = self.evaluate_pair()
        self.assert_protocol_equal(learned, frozen)
        self.assertEqual(learned["n_gallery"], 12)
        self.assertEqual(learned["primary"]["queries_evaluated"], 48)
        self.assertEqual(learned["primary"]["n_series"], 8)
        self.assertEqual(learned["team_context_control"]["queries_evaluated"], 48)
        for analysis in ("primary", "team_context_control"):
            self.assertEqual(learned[analysis]["metrics"]["top1"]["estimate"], 1.)
            self.assertEqual(learned[analysis]["null_stratum_sizes"], {"Europe": 12})

    def test_tied_vectors_keep_fractional_scores_for_both_candidate_masks(self):
        frame = self.frame.copy()
        frame[self.columns] = 1.
        learned, frozen = self.evaluate_pair(frame)
        self.assert_protocol_equal(learned, frozen)
        for analysis in ("primary", "team_context_control"):
            for metric in ("top1", "top5", "mrr"):
                values = learned[analysis]["metrics"][metric]
                self.assertAlmostEqual(values["estimate"], values["chance"], places=14)
                self.assertEqual(values["p_value"], 1.)

    def test_validation_region_does_not_reintroduce_unknown_training_region(self):
        metadata = copy.deepcopy(self.metadata)
        for row in metadata:
            if row["split"] == "train" and self.identities[0] in parsed_json(row["player_ids"], [])[:3]:
                row["region"] = None
        learned, frozen = self.evaluate_pair(metadata=metadata)
        self.assert_protocol_equal(learned, frozen)
        self.assertEqual(learned["excluded_unknown_train_region"], 3)
        self.assertEqual(learned["n_gallery"], 9)
        self.assertNotIn(self.identities[0], learned["eligible_ids"])

    def test_reference_comparison_rejects_input_and_population_mismatch(self):
        learned, handcrafted = self.evaluate_pair()
        reference = dict(copy.deepcopy(handcrafted), mode="full", **copy.deepcopy(self.source))
        comparison = compare_reference(reference, handcrafted, learned, self.source)
        self.assertTrue(comparison["same_protocol_population_and_source"])
        altered = copy.deepcopy(reference)
        altered["input_files"][0]["metadata_sha256"] = "synthetic-mismatch"
        comparison = compare_reference(altered, handcrafted, learned, self.source)
        self.assertFalse(comparison["same_protocol_population_and_source"])
        self.assertIn("input_metadata_and_shard_sizes", comparison["failed_checks"])
        altered = copy.deepcopy(learned)
        altered["primary"]["queries_evaluated"] -= 1
        comparison = compare_reference(reference, handcrafted, altered, self.source)
        self.assertFalse(comparison["same_protocol_population_and_source"])
        self.assertIn("primary_queries_evaluated", comparison["failed_checks"])

    def test_query_digest_tracks_identity_series_membership(self):
        learned, _ = self.evaluate_pair()
        keys = list(self.frame[self.frame.split == "val"].groupby(["identity_id", "series_id"], sort=True).groups)
        expected = hashlib.sha256(json.dumps(keys).encode()).hexdigest()
        self.assertEqual(learned["query_keys_sha256"], expected)


if __name__ == "__main__":
    unittest.main()
