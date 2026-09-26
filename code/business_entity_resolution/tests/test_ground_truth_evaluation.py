import tempfile
import unittest
from pathlib import Path

from src.evaluation import evaluate_predictions, score_entity
from src.ground_truth import create_split_from_ground_truth, load_ground_truth, parse_match_ids


class GroundTruthAndEvaluationTests(unittest.TestCase):
    def test_empty_one_multiple_and_both_sources(self):
        self.assertEqual(parse_match_ids(""), frozenset())
        self.assertEqual(parse_match_ids("S2-1"), frozenset({"S2-1"}))
        self.assertEqual(parse_match_ids("S2-1,S3-2,S2-3"), frozenset({"S2-1", "S3-2", "S2-3"}))

    def test_singleton_scoring(self):
        self.assertEqual(score_entity(frozenset(), frozenset()), (1.0, 1.0, 1.0))
        self.assertEqual(score_entity(frozenset(), {"S2-1"}), (0.0, 0.0, 0.0))

    def test_known_challenge_f05_example(self):
        precision, recall, f05 = score_entity({"S2-47", "S3-812"}, {"S2-47", "S2-193", "S3-812"})
        self.assertAlmostEqual(precision, 2 / 3)
        self.assertEqual(recall, 1.0)
        self.assertAlmostEqual(f05, 0.7142857142857143)

    def test_macro_metrics(self):
        result = evaluate_predictions({"S1-1": frozenset(), "S1-2": frozenset({"S2-1"})}, {"S1-2": {"S2-1"}})
        self.assertEqual(result.macro_f05, 1.0)
        self.assertEqual(result.singleton_accuracy, 1.0)
        self.assertEqual(result.singleton_false_positive_rate, 0.0)
        self.assertEqual(result.average_predicted_matches_per_s1, 0.5)

    def test_deterministic_disjoint_realistic_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); gt = root / "ground_truth.tsv"; output_a = root / "a"; output_b = root / "b"
            rows = ["source1_entity_id\tmatched_entity_ids"]
            rows.extend(f"S1-{number}\t" + ("S2-1,S3-1" if number % 3 == 0 else "S2-1" if number % 2 else "") for number in range(1, 31))
            gt.write_text("\n".join(rows) + "\n", encoding="utf-8")
            first = create_split_from_ground_truth(gt, output_a, seed=2026)
            second = create_split_from_ground_truth(gt, output_b, seed=2026)
            train = set((output_a / "train_source1_ids.txt").read_text().splitlines())
            validation = set((output_a / "validation_source1_ids.txt").read_text().splitlines())
            self.assertEqual(first["validation_source1_count"], second["validation_source1_count"])
            self.assertFalse(train & validation)
            self.assertEqual(len(train | validation), 30)

    def test_load_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gt.tsv"
            path.write_text("source1_entity_id\tmatched_entity_ids\nS1-1\tS2-1,S3-2\n", encoding="utf-8")
            self.assertEqual(load_ground_truth(path)["S1-1"], frozenset({"S2-1", "S3-2"}))


if __name__ == "__main__":
    unittest.main()
