#!/usr/bin/env python3
"""Streaming ground-truth parsing and compact, S1-level split creation."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

try:
    from .split import select_validation_ids, validation_targets
except ImportError:
    from split import select_validation_ids, validation_targets


class GroundTruthRecord(NamedTuple):
    source1_entity_id: str
    matched_entity_ids: frozenset[str]


def parse_match_ids(raw: str | None) -> frozenset[str]:
    """Parse an empty or comma-separated ID list without changing IDs."""
    if raw is None or raw == "":
        return frozenset()
    values = raw.split(",")
    if any(not value for value in values):
        raise ValueError("Ground-truth match list contains an empty ID entry")
    if len(values) != len(set(values)):
        raise ValueError("Ground-truth match list contains a duplicate ID")
    return frozenset(values)


def iter_ground_truth(path: Path) -> Iterator[GroundTruthRecord]:
    """Yield S1 -> immutable true-ID set records while keeping only one row in RAM."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected = ["source1_entity_id", "matched_entity_ids"]
        if reader.fieldnames != expected:
            raise ValueError(f"Expected columns {expected}, got {reader.fieldnames}")
        for row in reader:
            s1_id = row["source1_entity_id"]
            if not s1_id:
                raise ValueError("Ground truth contains a blank source1_entity_id")
            yield GroundTruthRecord(s1_id, parse_match_ids(row["matched_entity_ids"]))


def load_ground_truth(path: Path) -> dict[str, frozenset[str]]:
    """Load a mapping for small-data use/tests; use ``iter_ground_truth`` at scale."""
    result: dict[str, frozenset[str]] = {}
    for record in iter_ground_truth(path):
        if record.source1_entity_id in result:
            raise ValueError(f"Duplicate S1 ID: {record.source1_entity_id}")
        result[record.source1_entity_id] = record.matched_entity_ids
    return result


def _distribution(path: Path) -> Counter[int]:
    return Counter(len(record.matched_entity_ids) for record in iter_ground_truth(path))


def create_split_from_ground_truth(
    path: Path, output_dir: Path, seed: int = 2026, validation_fraction: float = 0.10
) -> dict:
    """Write train/validation S1 lists using three small streaming GT passes.

    This does not read source TSVs or duplicate them. The validation membership set
    is the only sizable in-memory structure (about 10% of S1 IDs).
    """
    totals = _distribution(path)
    targets = validation_targets(totals, validation_fraction)
    validation_ids = select_validation_ids(
        ((record.source1_entity_id, len(record.matched_entity_ids)) for record in iter_ground_truth(path)),
        targets,
        seed,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train_source1_ids.txt"
    validation_path = output_dir / "validation_source1_ids.txt"
    split_counts = {"train": Counter(), "validation": Counter()}
    with train_path.open("w", encoding="utf-8") as train_handle, validation_path.open("w", encoding="utf-8") as validation_handle:
        for record in iter_ground_truth(path):
            bucket = "validation" if record.source1_entity_id in validation_ids else "train"
            (validation_handle if bucket == "validation" else train_handle).write(record.source1_entity_id + "\n")
            split_counts[bucket][len(record.matched_entity_ids)] += 1
    metadata = {
        "seed": seed,
        "validation_fraction_requested": validation_fraction,
        "selection": "stable_blake2b_rank_stratified_by_complete_match_count",
        "ground_truth_path": str(path),
        "train_ids_path": str(train_path),
        "validation_ids_path": str(validation_path),
        "train_source1_count": sum(split_counts["train"].values()),
        "validation_source1_count": sum(split_counts["validation"].values()),
        "overlap_count": 0,
        "total_match_count_distribution": dict(sorted(totals.items())),
        "train_match_count_distribution": dict(sorted(split_counts["train"].items())),
        "validation_match_count_distribution": dict(sorted(split_counts["validation"].items())),
    }
    (output_dir / "split_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, default=Path("dataset/train/train_ground_truth.tsv"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/splits"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--validation-fraction", type=float, default=0.10)
    args = parser.parse_args()
    metadata = create_split_from_ground_truth(args.ground_truth, args.output_dir, args.seed, args.validation_fraction)
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
