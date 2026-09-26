import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.baseline import S1Record
from src.blocking import FrequencyCaps, blocking_keys
from src.candidate_generation import build_indexes, candidate_pass, merge_candidates
from src.normalization import normalize_business_address, normalize_business_name, normalize_country


def s1(entity_id, name, country="US", address="10 Main St"):
    return S1Record(entity_id, normalize_country(country).normalized, normalize_business_name(name), normalize_business_address(address))


class BlockingTests(unittest.TestCase):
    def _target_file(self, rows):
        temporary = tempfile.TemporaryDirectory(); path = Path(temporary.name) / "targets.tsv"
        path.write_text("entity_id\tbusiness_name\tbusiness_address\tcountry\n" + rows, encoding="utf-8")
        return temporary, path

    def test_exact_name_multiple_rules_and_deduplication(self):
        records = {"S1-1": s1("S1-1", "Acme Private Ltd")}; indexes = build_indexes(records)
        frequencies = {rule: {} for rule in indexes};
        for rule, keys in indexes.items():
            for key in keys: frequencies[rule][key] = 1
        tmp, path = self._target_file("S2-1\tACME PRIVATE LTD\t10 Main St\tUS\n")
        try:
            candidates, _, _ = candidate_pass(path, "S2", records, indexes, frequencies, FrequencyCaps({r: 1 for r in indexes}), {"S1-1": frozenset({"S2-1"})}, max_rows=None)
        finally: tmp.cleanup()
        self.assertEqual(set(candidates["S1-1"]), {"S2-1"})
        self.assertGreater(candidates["S1-1"]["S2-1"], 0)

    def test_high_frequency_key_suppression(self):
        records = {"S1-1": s1("S1-1", "Common Name")}; indexes = build_indexes(records)
        key = blocking_keys(records["S1-1"].country, records["S1-1"].name, records["S1-1"].address)["exact_name"][0]
        frequencies = {rule: {candidate_key: 99 for candidate_key in values} for rule, values in indexes.items()}; frequencies["exact_name"][key] = 99
        tmp, path = self._target_file("S2-1\tCommon Name\tx\tUS\n")
        try: candidates, _, _ = candidate_pass(path, "S2", records, indexes, frequencies, FrequencyCaps({r: 10 for r in indexes}), {"S1-1": frozenset({"S2-1"})})
        finally: tmp.cleanup()
        self.assertFalse(candidates.get("S1-1"))

    def test_rare_token_and_no_self_candidates(self):
        records = {"S1-1": s1("S1-1", "Zephyr Widgets", "Atlantis")}; indexes = build_indexes(records); frequencies = {rule: {key: 1 for key in values} for rule, values in indexes.items()}
        self.assertIn(("atlantis", "zephyr"), blocking_keys(records["S1-1"].country, records["S1-1"].name, records["S1-1"].address)["rare_token"])
        tmp, path = self._target_file("S3-1\tZephyr Tools\t99 Other\tAtlantis\nS1-9\tZephyr Widgets\t10 Main St\tAtlantis\n")
        try: candidates, _, _ = candidate_pass(path, "S3", records, indexes, frequencies, FrequencyCaps({r: 2 for r in indexes}), {"S1-1": frozenset({"S3-1"})})
        finally: tmp.cleanup()
        self.assertFalse(candidates.get("S1-1"))
        self.assertNotIn("S1-9", candidates["S1-1"])

    def test_merge_deterministic_and_empty(self):
        self.assertEqual(merge_candidates({}, {}), {})
        left = {"S1-1": {"S2-1": 1}}; right = {"S1-1": {"S2-1": 2, "S3-1": 4}}
        self.assertEqual(merge_candidates(left, right)["S1-1"], {"S2-1": 3, "S3-1": 4})


if __name__ == "__main__": unittest.main()
