#!/usr/bin/env python3
"""High-precision deterministic exact-normalization baseline.

The baseline builds inverted keys only for validation S1 records, then streams S2
and S3 once. It never compares every S1 to every target record or writes pairs.
"""

from __future__ import annotations

import argparse
import csv
import json
import resource
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from .evaluation import EvaluationResult, evaluate_predictions
    from .ground_truth import iter_ground_truth
    from .normalization import AddressNormalization, NameNormalization, normalize_business_address, normalize_business_name, normalize_country
except ImportError:
    from evaluation import EvaluationResult, evaluate_predictions
    from ground_truth import iter_ground_truth
    from normalization import AddressNormalization, NameNormalization, normalize_business_address, normalize_business_name, normalize_country

Progress = Callable[[str], None]


@dataclass(frozen=True)
class S1Record:
    entity_id: str
    country: str
    name: NameNormalization
    address: AddressNormalization


@dataclass
class BaselineResult:
    metrics: EvaluationResult
    prediction_counts: dict[str, float | int]
    coverage: dict[str, float | int]
    timings: dict[str, float]
    peak_rss_bytes: int
    examples: dict[str, list[str]]


def _read_id_file(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _progress(callback: Progress | None, message: str) -> None:
    if callback:
        callback(message)


def load_validation_s1(source1_path: Path, validation_ids: set[str], progress: Progress | None = print) -> dict[str, S1Record]:
    """Stream S1 and normalize only requested validation IDs."""
    records: dict[str, S1Record] = {}
    start = time.perf_counter()
    with source1_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            entity_id = row["entity_id"]
            if entity_id in validation_ids:
                records[entity_id] = S1Record(
                    entity_id=entity_id,
                    country=normalize_country(row["country"]).normalized,
                    name=normalize_business_name(row["business_name"]),
                    address=normalize_business_address(row["business_address"]),
                )
            if row_number % 500_000 == 0:
                _progress(progress, f"S1 scan: {row_number:,} rows; {len(records):,} validation records; {time.perf_counter()-start:.1f}s")
    if records.keys() != validation_ids:
        missing = len(validation_ids - records.keys())
        raise ValueError(f"Validation split has {missing} S1 IDs absent from source1")
    return records


def build_s1_indexes(records: dict[str, S1Record]) -> dict[str, dict[tuple[str, str], tuple[str, ...]]]:
    """Build immutable key -> S1 ID inverted indexes for exact baseline rules."""
    mutable: dict[str, defaultdict[tuple[str, str], list[str]]] = {
        "name": defaultdict(list), "core": defaultdict(list), "sorted": defaultdict(list)
    }
    for record in records.values():
        if record.name.normalized:
            mutable["name"][(record.country, record.name.normalized)].append(record.entity_id)
        if record.name.core_name:
            mutable["core"][(record.country, record.name.core_name)].append(record.entity_id)
        if record.name.sorted_tokens:
            mutable["sorted"][(record.country, record.name.sorted_tokens)].append(record.entity_id)
    return {kind: {key: tuple(ids) for key, ids in index.items()} for kind, index in mutable.items()}


def _add_candidate(predictions: dict[str, set[str]], suppressed: set[str], s1_id: str, target_id: str, max_candidates: int) -> None:
    if s1_id in suppressed:
        return
    candidates = predictions[s1_id]
    candidates.add(target_id)
    # Exact common-name buckets can be unbounded and are not high precision. The
    # ambiguity guard explicitly suppresses, rather than silently truncates, them.
    if len(candidates) > max_candidates:
        candidates.clear()
        suppressed.add(s1_id)


def stream_target_matches(
    target_path: Path,
    source_label: str,
    s1_records: dict[str, S1Record],
    indexes: dict[str, dict[tuple[str, str], tuple[str, ...]]],
    predictions: dict[str, set[str]],
    suppressed: set[str],
    max_candidates: int = 100,
    max_rows: int | None = None,
    progress: Progress | None = print,
) -> int:
    """Stream one target source and apply exact, country-consistent rules."""
    start = time.perf_counter()
    with target_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            if max_rows and row_number > max_rows:
                break
            country = normalize_country(row["country"]).normalized
            name = normalize_business_name(row["business_name"])
            address = normalize_business_address(row["business_address"])
            target_id = row["entity_id"]
            # Rule 1: exact full normalized name plus exact normalized country.
            matched_s1 = set(indexes["name"].get((country, name.normalized), ()))
            # Rules 2/3: legal-suffix or token-order-insensitive equivalence needs
            # exact normalized address agreement as additional precision support.
            if not address.is_missing:
                for kind, value in (("core", name.core_name), ("sorted", name.sorted_tokens)):
                    for s1_id in indexes[kind].get((country, value), ()):
                        s1 = s1_records[s1_id]
                        if not s1.address.is_missing and s1.address.compact == address.compact:
                            matched_s1.add(s1_id)
            for s1_id in matched_s1:
                _add_candidate(predictions, suppressed, s1_id, target_id, max_candidates)
            if row_number % 500_000 == 0:
                elapsed = time.perf_counter() - start
                _progress(progress, f"{source_label} scan: {row_number:,} rows; {elapsed:.1f}s; {row_number/elapsed:,.0f} rows/s")
    return min(row_number if 'row_number' in locals() else 0, max_rows) if max_rows else (row_number if 'row_number' in locals() else 0)


def load_validation_truth(ground_truth_path: Path, validation_ids: set[str]) -> dict[str, frozenset[str]]:
    """Stream GT and retain labels for validation S1 only."""
    truth = {record.source1_entity_id: record.matched_entity_ids for record in iter_ground_truth(ground_truth_path) if record.source1_entity_id in validation_ids}
    if truth.keys() != validation_ids:
        raise ValueError("Validation IDs and ground-truth IDs differ")
    return truth


def _examples(truth: dict[str, frozenset[str]], predictions: dict[str, set[str]], limit: int = 5) -> dict[str, list[str]]:
    false_negatives, false_positives = [], []
    for s1_id in sorted(truth):
        true, predicted = truth[s1_id], predictions.get(s1_id, set())
        if true - predicted and len(false_negatives) < limit:
            false_negatives.append(f"{s1_id}: missed={len(true-predicted)}, predicted={len(predicted)}, true={len(true)}")
        if predicted - true and len(false_positives) < limit:
            false_positives.append(f"{s1_id}: false_positive={len(predicted-true)}, predicted={len(predicted)}, true={len(true)}")
    return {"false_negative_examples": false_negatives, "false_positive_examples": false_positives}


def run_baseline(
    source1_path: Path, source2_path: Path, source3_path: Path, ground_truth_path: Path,
    validation_ids_path: Path, max_target_rows: int | None = None, progress: Progress | None = print,
) -> BaselineResult:
    """Run the baseline end-to-end, optionally bounding each target scan for sampling."""
    total_start = time.perf_counter()
    validation_ids = _read_id_file(validation_ids_path)
    s1_start = time.perf_counter()
    s1_records = load_validation_s1(source1_path, validation_ids, progress)
    indexes = build_s1_indexes(s1_records)
    s1_seconds = time.perf_counter() - s1_start
    predictions: dict[str, set[str]] = defaultdict(set)
    suppressed: set[str] = set()
    target_start = time.perf_counter()
    rows2 = stream_target_matches(source2_path, "S2", s1_records, indexes, predictions, suppressed, max_rows=max_target_rows, progress=progress)
    rows3 = stream_target_matches(source3_path, "S3", s1_records, indexes, predictions, suppressed, max_rows=max_target_rows, progress=progress)
    target_seconds = time.perf_counter() - target_start
    truth = load_validation_truth(ground_truth_path, validation_ids)
    metrics = evaluate_predictions(truth, predictions)
    counts = [len(predictions.get(s1_id, set())) for s1_id in validation_ids]
    count_histogram = Counter(counts)
    count = len(counts)
    prediction_counts = {
        "average_predicted_matches_per_s1": sum(counts) / count,
        "median_predicted_matches_per_s1": statistics.median(counts),
        "no_prediction_percentage": 100 * count_histogram[0] / count,
        "one_prediction_percentage": 100 * count_histogram[1] / count,
        "multiple_prediction_percentage": 100 * sum(value for key, value in count_histogram.items() if key > 1) / count,
        "suppressed_ambiguous_s1": len(suppressed),
    }
    coverage = {"validation_s1_with_candidate": count - count_histogram[0], "validation_s1_zero_candidates": count_histogram[0], "candidate_coverage_percentage": 100 * (count-count_histogram[0]) / count}
    return BaselineResult(
        metrics=metrics, prediction_counts=prediction_counts, coverage=coverage,
        timings={"s1_index_seconds": s1_seconds, "target_scan_seconds": target_seconds, "total_seconds": time.perf_counter()-total_start, "s2_rows": rows2, "s3_rows": rows3},
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, examples=_examples(truth, predictions),
    )


def format_report(result: BaselineResult) -> str:
    return "# Phase 4 Deterministic Baseline Results\n\n```json\n" + json.dumps({"metrics": result.metrics.__dict__, "prediction_statistics": result.prediction_counts, "coverage": result.coverage, "timings": result.timings, "peak_rss_bytes": result.peak_rss_bytes, "examples": result.examples}, indent=2, sort_keys=True) + "\n```\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source1", type=Path, default=Path("dataset/train/train_source1.tsv"))
    parser.add_argument("--source2", type=Path, default=Path("dataset/train/train_source2.tsv"))
    parser.add_argument("--source3", type=Path, default=Path("dataset/train/train_source3.tsv"))
    parser.add_argument("--ground-truth", type=Path, default=Path("dataset/train/train_ground_truth.tsv"))
    parser.add_argument("--validation-ids", type=Path, default=Path("reports/splits/validation_source1_ids.txt"))
    parser.add_argument("--report", type=Path, default=Path("reports/baseline_results.md"))
    parser.add_argument("--sample-target-rows", type=int)
    args = parser.parse_args()
    result = run_baseline(args.source1, args.source2, args.source3, args.ground_truth, args.validation_ids, args.sample_target_rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(format_report(result), encoding="utf-8")
    print(json.dumps(result.timings, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
