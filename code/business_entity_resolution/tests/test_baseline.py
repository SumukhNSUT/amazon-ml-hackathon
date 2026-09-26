import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from src.baseline import S1Record, build_s1_indexes, stream_target_matches
from src.normalization import normalize_business_address, normalize_business_name, normalize_country


def record(entity_id, name, country="US", address="1 Main St"):
    return S1Record(entity_id, normalize_country(country).normalized, normalize_business_name(name), normalize_business_address(address))


class BaselineTests(unittest.TestCase):
    def _targets(self, text):
        temporary = tempfile.TemporaryDirectory(); path = Path(temporary.name) / "targets.tsv"
        path.write_text("entity_id\tbusiness_name\tbusiness_address\tcountry\n" + text, encoding="utf-8")
        return temporary, path

    def test_exact_name_and_multiple_matches(self):
        records = {"S1-1": record("S1-1", "Acme Inc")}; indexes = build_s1_indexes(records); predictions = defaultdict(set)
        tmp, path = self._targets("S2-1\tACME INC\tOther\tUS\nS3-1\tAcme Inc\tx\tUS\n")
        try: stream_target_matches(path, "T", records, indexes, predictions, set(), progress=None)
        finally: tmp.cleanup()
        self.assertEqual(predictions["S1-1"], {"S2-1", "S3-1"})

    def test_zero_matches_and_country_consistency(self):
        records = {"S1-1": record("S1-1", "Acme", "US")}; indexes = build_s1_indexes(records); predictions = defaultdict(set)
        tmp, path = self._targets("S2-1\tAcme\t1 Main St\tCanada\n")
        try: stream_target_matches(path, "T", records, indexes, predictions, set(), progress=None)
        finally: tmp.cleanup()
        self.assertFalse(predictions["S1-1"])

    def test_core_name_requires_matching_nonmissing_address(self):
        records = {"S1-1": record("S1-1", "Acme Private Limited", address="10 Road")}; indexes = build_s1_indexes(records); predictions = defaultdict(set)
        tmp, path = self._targets("S2-1\tAcme Ltd\t\tUS\nS2-2\tAcme Ltd\t10 Road\tUS\n")
        try: stream_target_matches(path, "T", records, indexes, predictions, set(), progress=None)
        finally: tmp.cleanup()
        self.assertEqual(predictions["S1-1"], {"S2-2"})

    def test_deterministic_behavior(self):
        records = {"S1-1": record("S1-1", "A & B")}; indexes = build_s1_indexes(records)
        tmp, path = self._targets("S2-1\tA and B\tx\tUS\n")
        try:
            first, second = defaultdict(set), defaultdict(set)
            stream_target_matches(path, "T", records, indexes, first, set(), progress=None)
            stream_target_matches(path, "T", records, indexes, second, set(), progress=None)
        finally: tmp.cleanup()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
