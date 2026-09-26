import unittest

from src.normalization import (
    normalize_business_address,
    normalize_business_name,
    normalize_country,
    normalize_record,
)


class NormalizationTests(unittest.TestCase):
    def test_case_punctuation_whitespace_and_ampersand(self):
        value = normalize_business_name("  ACME & Sons, Inc.  ")
        self.assertEqual(value.normalized, "acme and sons inc")
        self.assertEqual(value.alphanumeric, "acmeandsonsinc")
        self.assertEqual(value.core_name, "acme and sons")

    def test_legal_suffix_variants_and_token_reordering(self):
        first = normalize_business_name("Bright Star Pvt. Ltd")
        second = normalize_business_name("Ltd Bright Star Private")
        self.assertEqual(first.core_name, "bright star")
        self.assertEqual(second.core_name, "bright star")
        self.assertEqual(first.sorted_tokens, "bright ltd pvt star")

    def test_unicode_normalization_preserves_non_latin_script(self):
        value = normalize_business_name("ＣＡＦＥ　मॉडर्न")
        self.assertEqual(value.normalized, "cafe मॉडर्न")
        self.assertIn("मॉडर्न", value.tokens)

    def test_address_missing_numbers_and_postal_tokens(self):
        missing = normalize_business_address(None)
        address = normalize_business_address(" 10-B, Main Rd., New Delhi 110001; ZIP 02139-1234 ")
        self.assertTrue(missing.is_missing)
        self.assertEqual(missing.tokens, ())
        self.assertEqual(address.numeric_tokens, ("10", "110001", "02139", "1234"))
        self.assertIn("110001", address.postal_tokens)
        self.assertIn("02139-1234", address.postal_tokens)

    def test_open_set_country_and_raw_record_preservation(self):
        country = normalize_country("  Côte d’Ivoire ")
        raw = {"business_name": "New Co", "business_address": None, "country": "Atlantis"}
        result = normalize_record(raw)
        self.assertEqual(country.normalized, "côte d ivoire")
        self.assertFalse(country.is_missing)
        self.assertEqual(result["country_normalized"]["normalized"], "atlantis")
        self.assertEqual(result["business_name"], "New Co")
        self.assertIsNone(result["business_address"])

    def test_deterministic(self):
        value = "Example & Company, LLC"
        self.assertEqual(normalize_business_name(value), normalize_business_name(value))


if __name__ == "__main__":
    unittest.main()
