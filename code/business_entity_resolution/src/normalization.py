"""Conservative, deterministic normalizers for entity-resolution text fields.

Functions accept raw strings (including ``None``), return immutable value objects,
and never mutate or discard caller-owned raw columns. They are intended for
row-wise or chunk-wise application, not for materializing a full normalized corpus.
"""

from __future__ import annotations

import csv
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from itertools import islice
from pathlib import Path
from typing import Iterable

# Conservative common legal/designator terms. These are only removed from the
# *core* name representation; the full normalized tokens remain available.
LEGAL_SUFFIXES = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "llc", "llp", "plc", "pvt", "private", "sa", "sas", "sarl",
    "gmbh", "ag", "bv", "nv", "oy", "ab", "pte", "pty", "kg", "kft",
})

_WHITESPACE_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"\d+")
_POSTAL_RE = re.compile(r"(?<!\w)(?:\d{5}-\d{4}|\d{4,10}|[a-z]\d[a-z][ -]?\d[a-z]\d)(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class NameNormalization:
    normalized: str
    alphanumeric: str
    tokens: tuple[str, ...]
    core_name: str
    sorted_tokens: str


@dataclass(frozen=True)
class AddressNormalization:
    normalized: str
    compact: str
    tokens: tuple[str, ...]
    numeric_tokens: tuple[str, ...]
    postal_tokens: tuple[str, ...]
    is_missing: bool


@dataclass(frozen=True)
class CountryNormalization:
    normalized: str
    is_missing: bool


def _text(value: object | None) -> str:
    """NFKC-normalize and case-fold arbitrary nullable input without transliteration."""
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).casefold()


def _clean_text(value: object | None) -> str:
    text = _text(value).replace("&", " and ")
    # Keep letters, digits, and combining marks intact in every script; replace
    # only Unicode punctuation/symbol categories with separators.
    text = "".join(" " if unicodedata.category(char)[0] in {"P", "S"} else char for char in text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_business_name(value: object | None) -> NameNormalization:
    """Create loss-limited name forms; only ``core_name`` removes legal suffixes."""
    normalized = _clean_text(value)
    # Splitting cleaned whitespace preserves combining marks in scripts such as
    # Devanagari, unlike Python's ``\w+`` regular-expression class.
    tokens = tuple(normalized.split())
    core_tokens = tuple(token for token in tokens if token not in LEGAL_SUFFIXES)
    return NameNormalization(
        normalized=normalized,
        alphanumeric="".join(tokens),
        tokens=tokens,
        core_name=" ".join(core_tokens),
        sorted_tokens=" ".join(sorted(tokens)),
    )


def normalize_business_address(value: object | None) -> AddressNormalization:
    """Create reusable address forms without attempting geocoding or expansion."""
    source = _text(value)
    normalized = _clean_text(value)
    tokens = tuple(normalized.split())
    # Search before punctuation cleanup so ZIP+4 and comparable forms are retained.
    postal_tokens = tuple(match.group(0).replace(" ", "").lower() for match in _POSTAL_RE.finditer(source))
    return AddressNormalization(
        normalized=normalized,
        compact="".join(tokens),
        tokens=tokens,
        numeric_tokens=tuple(_NUMBER_RE.findall(normalized)),
        postal_tokens=postal_tokens,
        is_missing=not normalized,
    )


def normalize_country(value: object | None) -> CountryNormalization:
    """Normalize an open-set country string without mapping to a fixed vocabulary."""
    normalized = _clean_text(value)
    return CountryNormalization(normalized=normalized, is_missing=not normalized)


def normalize_record(record: dict[str, object | None]) -> dict[str, object]:
    """Return normalized derivatives while retaining all raw record fields unchanged."""
    output: dict[str, object] = dict(record)
    output["name_normalized"] = asdict(normalize_business_name(record.get("business_name")))
    output["address_normalized"] = asdict(normalize_business_address(record.get("business_address")))
    output["country_normalized"] = asdict(normalize_country(record.get("country")))
    return output


def benchmark_tsv_sample(path: Path, sample_size: int = 10_000) -> dict[str, float | int]:
    """Benchmark bounded streaming normalization; never retain normalized rows."""
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    start = time.perf_counter()
    rows = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for record in islice(csv.DictReader(handle, delimiter="\t"), sample_size):
            normalize_record(record)
            rows += 1
    elapsed = time.perf_counter() - start
    return {"rows": rows, "elapsed_seconds": elapsed, "rows_per_second": rows / elapsed if elapsed else 0.0}
