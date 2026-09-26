#!/usr/bin/env python3
"""Validation-only scalable multi-pass candidate generation and analysis."""

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

try:
    from .baseline import S1Record, load_validation_s1
    from .blocking import RULE_BITS, RULES, SELECTED_RULES, FrequencyCaps, blocking_keys
    from .ground_truth import iter_ground_truth
    from .normalization import normalize_business_address, normalize_business_name, normalize_country
except ImportError:
    from baseline import S1Record, load_validation_s1
    from blocking import RULE_BITS, RULES, SELECTED_RULES, FrequencyCaps, blocking_keys
    from ground_truth import iter_ground_truth
    from normalization import normalize_business_address, normalize_business_name, normalize_country


def read_ids(path: Path, limit: int | None = None) -> set[str]:
    values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return set(values[:limit]) if limit else set(values)


def build_indexes(records: dict[str, S1Record]) -> dict[str, dict[tuple[str, str], tuple[str, ...]]]:
    indexes = {rule: defaultdict(list) for rule in RULES}
    for record in records.values():
        for rule, keys in blocking_keys(record.country, record.name, record.address).items():
            for key in keys:
                indexes[rule][key].append(record.entity_id)
    return {rule: {key: tuple(ids) for key, ids in values.items()} for rule, values in indexes.items()}


def scan_frequencies(path: Path, indexes: dict, source: str, max_rows: int | None = None) -> tuple[dict[str, dict[tuple[str, str], int]], int]:
    """Count only target keys that are present in validation-S1 indexes."""
    frequencies = {rule: Counter() for rule in RULES}; start = time.perf_counter(); rows = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows += 1
            if max_rows and rows > max_rows: break
            country = normalize_country(row["country"]).normalized
            keys = blocking_keys(country, normalize_business_name(row["business_name"]), normalize_business_address(row["business_address"]))
            for rule, rule_keys in keys.items():
                index = indexes[rule]
                for key in rule_keys:
                    if key in index: frequencies[rule][key] += 1
            if rows % 500_000 == 0:
                elapsed = time.perf_counter() - start
                print(f"frequency {source}: {rows:,} rows; {elapsed:.1f}s; {rows/elapsed:,.0f} rows/s", flush=True)
    return {rule: dict(value) for rule, value in frequencies.items()}, min(rows, max_rows) if max_rows else rows


def candidate_pass(path: Path, source: str, records: dict[str, S1Record], indexes: dict, frequencies: dict, caps: FrequencyCaps, truth: dict[str, frozenset[str]], max_rows: int | None = None, candidates: dict[str, dict[str, int]] | None = None) -> tuple[dict[str, dict[str, int]], dict[str, Counter], int]:
    """Create deduplicated candidate rule masks, respecting observed frequency caps."""
    candidates = candidates if candidates is not None else defaultdict(dict)
    rule_pairs = {rule: Counter() for rule in RULES}; start = time.perf_counter(); rows = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows += 1
            if max_rows and rows > max_rows: break
            target_id = row["entity_id"]
            if not target_id.startswith(source + "-"):
                continue
            country = normalize_country(row["country"]).normalized
            keys = blocking_keys(country, normalize_business_name(row["business_name"]), normalize_business_address(row["business_address"]))
            for rule, rule_keys in keys.items():
                if rule not in SELECTED_RULES:
                    continue
                for key in rule_keys:
                    if frequencies[rule].get(key, 0) > caps.caps[rule]:
                        continue
                    for s1_id in indexes[rule].get(key, ()):
                        prior = candidates[s1_id].get(target_id, 0)
                        candidates[s1_id][target_id] = prior | RULE_BITS[rule]
                        rule_pairs[rule]["pairs"] += int(prior == 0 or not (prior & RULE_BITS[rule]))
                        if target_id in truth[s1_id]: rule_pairs[rule]["true_links"] += 1
            if rows % 500_000 == 0:
                elapsed = time.perf_counter() - start; pair_count = sum(len(value) for value in candidates.values())
                print(f"candidates {source}: {rows:,} rows; {pair_count:,} pairs; {elapsed:.1f}s; {rows/elapsed:,.0f} rows/s", flush=True)
    return candidates, rule_pairs, min(rows, max_rows) if max_rows else rows


def merge_candidates(left: dict[str, dict[str, int]], right: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    merged = {s1: dict(targets) for s1, targets in left.items()}
    for s1, targets in right.items():
        destination = merged.setdefault(s1, {})
        for target, mask in targets.items(): destination[target] = destination.get(target, 0) | mask
    return merged


def load_truth(path: Path, ids: set[str]) -> dict[str, frozenset[str]]:
    return {record.source1_entity_id: record.matched_entity_ids for record in iter_ground_truth(path) if record.source1_entity_id in ids}


def summarize(records: dict[str, S1Record], truth: dict[str, frozenset[str]], candidates: dict[str, dict[str, int]], rule_pairs: dict[str, Counter], caps: FrequencyCaps) -> tuple[dict, list[dict]]:
    true_total = sum(len(value) for value in truth.values()); true_by_source = {"S2": sum(sum(item.startswith("S2-") for item in values) for values in truth.values()), "S3": sum(sum(item.startswith("S3-") for item in values) for values in truth.values())}
    found_by_source = Counter(); found_masks: Counter[int] = Counter(); counts = []
    for s1, true_ids in truth.items():
        predicted = candidates.get(s1, {}); counts.append(len(predicted))
        for target in true_ids:
            if target in predicted:
                found_by_source[target[:2]] += 1; found_masks[predicted[target]] += 1
    total_pairs = sum(counts); all_pairs = len(records) * (5_034_616 + 5_285_603)
    rows = []
    for rule in RULES:
        bit = RULE_BITS[rule]
        hit = sum(count for mask, count in found_masks.items() if mask & bit)
        unique = found_masks.get(bit, 0)
        rows.append({"rule": rule, "frequency_cap": caps.caps[rule], "candidate_events": rule_pairs[rule]["pairs"], "true_links_found": hit, "unique_true_links": unique, "rule_recall": hit/true_total if true_total else 0.0, "incremental_unique_recall": unique/true_total if true_total else 0.0})
    summary = {"true_links_total": true_total, "s2_true_links": true_by_source["S2"], "s3_true_links": true_by_source["S3"], "s2_found": found_by_source["S2"], "s3_found": found_by_source["S3"], "combined_found": sum(found_by_source.values()), "s2_recall": found_by_source["S2"]/true_by_source["S2"], "s3_recall": found_by_source["S3"]/true_by_source["S3"], "combined_recall": sum(found_by_source.values())/true_total, "total_candidate_pairs": total_pairs, "average_candidates_per_s1": statistics.mean(counts), "median_candidates_per_s1": statistics.median(counts), "p90_candidates_per_s1": statistics.quantiles(counts, n=10)[8], "p95_candidates_per_s1": statistics.quantiles(counts, n=20)[18], "p99_candidates_per_s1": statistics.quantiles(counts, n=100)[98], "max_candidates_per_s1": max(counts), "zero_candidate_s1": counts.count(0), "zero_candidate_percentage": 100*counts.count(0)/len(counts), "reduction_ratio": 1 - total_pairs/all_pairs, "all_pairs": all_pairs, "true_matches_missed": true_total-sum(found_by_source.values())}
    return summary, rows


def write_key_stats(path: Path, frequencies: dict, caps: FrequencyCaps) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rule", "s1_relevant_keys_hit", "min_target_frequency", "median_target_frequency", "p90_target_frequency", "p95_target_frequency", "p99_target_frequency", "max_target_frequency", "selected_frequency_cap"]); writer.writeheader()
        for rule in RULES:
            values = sorted(frequencies[rule].values())
            def q(p): return values[min(len(values)-1, round((len(values)-1)*p))] if values else 0
            writer.writerow({"rule": rule, "s1_relevant_keys_hit": len(values), "min_target_frequency": min(values) if values else 0, "median_target_frequency": q(.5), "p90_target_frequency": q(.9), "p95_target_frequency": q(.95), "p99_target_frequency": q(.99), "max_target_frequency": max(values) if values else 0, "selected_frequency_cap": caps.caps[rule]})


def write_rule_results(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-ids", type=Path, default=Path("reports/splits/validation_source1_ids.txt")); parser.add_argument("--sample-s1", type=int); parser.add_argument("--max-target-rows", type=int)
    parser.add_argument("--source1", type=Path, default=Path("dataset/train/train_source1.tsv")); parser.add_argument("--source2", type=Path, default=Path("dataset/train/train_source2.tsv")); parser.add_argument("--source3", type=Path, default=Path("dataset/train/train_source3.tsv")); parser.add_argument("--ground-truth", type=Path, default=Path("dataset/train/train_ground_truth.tsv")); parser.add_argument("--reports", type=Path, default=Path("reports"))
    args = parser.parse_args(); start = time.perf_counter(); ids = read_ids(args.validation_ids, args.sample_s1); records = load_validation_s1(args.source1, ids); truth = load_truth(args.ground_truth, ids); indexes = build_indexes(records)
    f2, _ = scan_frequencies(args.source2, indexes, "S2", args.max_target_rows); f3, _ = scan_frequencies(args.source3, indexes, "S3", args.max_target_rows); frequencies = {rule: Counter(f2[rule]) + Counter(f3[rule]) for rule in RULES}; caps = FrequencyCaps.from_frequencies(frequencies)
    candidates, r2, _ = candidate_pass(args.source2, "S2", records, indexes, frequencies, caps, truth, args.max_target_rows); candidates, r3, _ = candidate_pass(args.source3, "S3", records, indexes, frequencies, caps, truth, args.max_target_rows, candidates); rule_pairs = {rule: r2[rule] + r3[rule] for rule in RULES}; summary, rule_rows = summarize(records, truth, candidates, rule_pairs, caps)
    args.reports.mkdir(exist_ok=True); write_key_stats(args.reports / "blocking_key_statistics.csv", frequencies, caps); write_rule_results(args.reports / "blocking_rule_results.csv", rule_rows)
    payload = {"summary": summary, "rules": rule_rows, "runtime_seconds": time.perf_counter()-start, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}; (args.reports / "blocking_run.json").write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8"); print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
