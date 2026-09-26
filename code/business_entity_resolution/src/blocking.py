"""Deterministic blocking keys and frequency-controlled candidate utilities."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from .normalization import AddressNormalization, NameNormalization
except ImportError:
    from normalization import AddressNormalization, NameNormalization


RULES = ("exact_name", "core_name", "sorted_name", "rare_token", "name_prefix", "postal", "name_number")
SELECTED_RULES = ("exact_name", "core_name", "sorted_name", "postal", "name_number")
RULE_BITS = {rule: 1 << index for index, rule in enumerate(RULES)}


def _key(country: str, value: str) -> tuple[str, str] | None:
    return (country, value) if country and value else None


def name_tokens(name: NameNormalization) -> tuple[str, ...]:
    """Deduplicated, conservative informative tokens (not stop-word expanded)."""
    return tuple(sorted({token for token in name.tokens if len(token) >= 4 and not token.isdigit()}))


def name_prefix(name: NameNormalization) -> str:
    return name.alphanumeric[:6] if len(name.alphanumeric) >= 6 else ""


def blocking_keys(country: str, name: NameNormalization, address: AddressNormalization) -> dict[str, tuple[tuple[str, str], ...]]:
    """Return open-set-country blocking keys; empty/unsafe representations omitted."""
    result: dict[str, tuple[tuple[str, str], ...]] = {}
    for rule, values in {
        "exact_name": (name.normalized,), "core_name": (name.core_name,),
        "sorted_name": (name.sorted_tokens,), "rare_token": name_tokens(name),
        "name_prefix": (name_prefix(name),), "postal": address.postal_tokens,
    }.items():
        result[rule] = tuple(key for value in values if (key := _key(country, value)))
    # A name token with a street/building number is much more selective than either.
    if address.numeric_tokens and name_tokens(name):
        result["name_number"] = tuple(_key(country, f"{token}|{number}") for token in name_tokens(name)[:3] for number in address.numeric_tokens[:2])
    else:
        result["name_number"] = ()
    return result


def percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * p))
    return ordered[index]


@dataclass(frozen=True)
class FrequencyCaps:
    """Per-rule caps derived from observed S1-relevant target-key frequencies."""
    caps: dict[str, int]

    @classmethod
    def from_frequencies(cls, frequencies: dict[str, dict[tuple[str, str], int]], percentile_value: float = 0.95) -> "FrequencyCaps":
        return cls({rule: max(1, percentile(list(counts.values()), percentile_value)) for rule, counts in frequencies.items()})
