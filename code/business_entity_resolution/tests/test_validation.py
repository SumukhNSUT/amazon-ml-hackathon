import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.data_validation import id_status, parse_match_list, validate_ground_truth, validate_source, open_database
from src.split import select_validation_ids, validation_targets


class ValidationUnitTests(unittest.TestCase):
    def test_malformed_and_missing_ids(self):
        self.assertEqual(id_status("bad", "S1"), "malformed_id")
        self.assertEqual(id_status("", "S1"), "missing_id")
        self.assertEqual(id_status("S2-7", "S1"), "unexpected_source_prefix")

    def test_duplicate_ids_and_blank_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "train_source1.tsv"
            path.write_text("entity_id\tbusiness_name\tbusiness_address\tcountry\nS1-1\tA\tx\tUS\nS1-1\t\tx\tUS\n")
            conn = open_database(root)
            result = validate_source(path, conn)
            self.assertEqual(result["issues"]["duplicate_entity_id"], 1)
            self.assertEqual(result["issues"]["blank_required_business_name"], 1)
            conn.close()

    def test_invalid_gt_references_self_match_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "train_source1.tsv").write_text("entity_id\tbusiness_name\tbusiness_address\tcountry\nS1-1\tA\tx\tUS\n")
            (root / "train_source2.tsv").write_text("entity_id\tbusiness_name\tbusiness_address\tcountry\nS2-1\tA\tx\tUS\n")
            (root / "train_source3.tsv").write_text("entity_id\tbusiness_name\tbusiness_address\tcountry\nS3-1\tA\tx\tUS\n")
            gt = root / "train_ground_truth.tsv"
            gt.write_text("source1_entity_id\tmatched_entity_ids\nS1-1\tS1-1,S2-1,S2-1,S2-404\n")
            conn = open_database(root)
            for source in (root / "train_source1.tsv", root / "train_source2.tsv", root / "train_source3.tsv"):
                validate_source(source, conn)
            result = validate_ground_truth(gt, conn)
            self.assertEqual(result["issues"]["s1_in_match_list"], 1)
            self.assertEqual(result["issues"]["duplicate_target_within_match_list"], 1)
            self.assertEqual(result["issues"]["unknown_target_reference"], 1)
            conn.close()

    def test_empty_match_entry_is_rejected(self):
        self.assertIsNone(parse_match_list("S2-1,,S3-1"))

    def test_deterministic_disjoint_split(self):
        records = [(f"S1-{n}", n % 3) for n in range(30)]
        targets = validation_targets(Counter(count for _, count in records), 0.2)
        first = select_validation_ids(records, targets, 2026)
        second = select_validation_ids(records, targets, 2026)
        train = {entity_id for entity_id, _ in records} - first
        self.assertEqual(first, second)
        self.assertFalse(first & train)
        self.assertEqual(len(first), sum(targets.values()))


if __name__ == "__main__":
    unittest.main()
