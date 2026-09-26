"""Deterministic, S1-level stratified split utilities."""

from __future__ import annotations

import hashlib
import heapq
from collections import Counter, defaultdict
from collections.abc import Iterable


def stable_hash(entity_id: str, seed: int) -> int:
    """Return a reproducible unsigned 64-bit rank for an entity ID."""
    value = f"{seed}:{entity_id}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(value, digest_size=8).digest(), "big")


def validation_targets(stratum_counts: Counter[int], fraction: float) -> dict[int, int]:
    """Choose an exact target count per stratum, retaining tiny strata in train."""
    if not 0 < fraction < 1:
        raise ValueError("fraction must be strictly between 0 and 1")
    return {
        stratum: min(count - 1, max(1, round(count * fraction))) if count > 1 else 0
        for stratum, count in stratum_counts.items()
    }


def select_validation_ids(
    records: Iterable[tuple[str, int]], targets: dict[int, int], seed: int
) -> set[str]:
    """Select the lowest stable-hash IDs per match-count stratum.

    Memory is O(number of validation IDs), rather than O(number of all source-1
    records). ``records`` may be a streaming iterator.
    """
    heaps: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for entity_id, stratum in records:
        target = targets.get(stratum, 0)
        if not target:
            continue
        # A negative rank turns heapq's min-heap into a max-heap.  Include the ID
        # for a deterministic tie breaker (practically unnecessary for 64 bits).
        item = (-stable_hash(entity_id, seed), entity_id)
        heap = heaps[stratum]
        if len(heap) < target:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    return {entity_id for heap in heaps.values() for _, entity_id in heap}
