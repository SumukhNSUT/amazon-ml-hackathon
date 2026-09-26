#!/usr/bin/env python3
"""Streaming validation for the ML Challenge 2026 input TSVs.

The module deliberately uses a temporary SQLite index for source IDs. This keeps
peak Python memory low while allowing duplicate and ground-truth reference checks
over the full challenge corpus.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:  # package import for tests and installed use
    from .split import select_validation_ids, validation_targets
except ImportError:  # direct `python src/data_validation.py` execution
    from split import select_validation_ids, validation_targets

EXPECTED_SOURCE_COLUMNS = ["entity_id", "business_name", "business_address", "country"]
EXPECTED_GT_COLUMNS = ["source1_entity_id", "matched_entity_ids"]
ID_PREFIXES = {"S1", "S2", "S3"}


@dataclass
class Issues:
    counts: Counter = field(default_factory=Counter)
    examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add(self, kind: str, value: str, limit: int = 5) -> None:
        self.counts[kind] += 1
        if len(self.examples[kind]) < limit:
            self.examples[kind].append(value)


def blank(value: str | None) -> bool:
    return value is None or not value.strip()


def id_status(entity_id: str, expected_prefix: str) -> str | None:
    """Return the first ID defect, or None for a valid source-local ID."""
    if blank(entity_id):
        return "missing_id"
    parts = entity_id.split("-", 1)
    if len(parts) != 2 or parts[0] not in ID_PREFIXES or not parts[1].isdigit():
        return "malformed_id"
    if parts[0] != expected_prefix:
        return "unexpected_source_prefix"
    return None


def require_columns(fieldnames: list[str] | None, expected: list[str], label: str) -> None:
    if fieldnames != expected:
        raise ValueError(f"{label}: expected columns {expected}, found {fieldnames}")


def source_file_spec(path: Path) -> tuple[str, str]:
    name = path.name
    if "source1" in name:
        return "S1", "source1"
    if "source2" in name:
        return "S2", "source2"
    if "source3" in name:
        return "S3", "source3"
    raise ValueError(f"Cannot infer expected source from {path}")


def open_database(temp_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(temp_dir / "ids.sqlite")
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("CREATE TABLE ids (entity_id TEXT PRIMARY KEY, source TEXT NOT NULL)")
    conn.execute("CREATE TABLE ground_truth_s1 (entity_id TEXT PRIMARY KEY, match_count INTEGER NOT NULL)")
    conn.execute("CREATE TABLE target_reuse (entity_id TEXT PRIMARY KEY, reference_count INTEGER NOT NULL)")
    return conn


def validate_source(path: Path, conn: sqlite3.Connection) -> dict:
    expected_prefix, label = source_file_spec(path)
    issues = Issues()
    countries: Counter[str] = Counter()
    rows = 0
    address_blank = 0
    start = time.perf_counter()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        require_columns(reader.fieldnames, EXPECTED_SOURCE_COLUMNS, str(path))
        for row in reader:
            rows += 1
            entity_id = row["entity_id"]
            status = id_status(entity_id, expected_prefix)
            if status:
                issues.add(status, entity_id or "<blank>")
            elif conn.execute(
                "INSERT OR IGNORE INTO ids(entity_id, source) VALUES (?, ?)",
                (entity_id, expected_prefix),
            ).rowcount == 0:
                issues.add("duplicate_entity_id", entity_id)
            for column in ("business_name", "country"):
                if blank(row[column]):
                    issues.add(f"blank_required_{column}", entity_id or "<blank>")
            if blank(row["business_address"]):
                address_blank += 1
            if not blank(row["country"]):
                countries[row["country"]] += 1
    conn.commit()
    return {
        "label": label,
        "path": str(path),
        "rows": rows,
        "unique_valid_ids": conn.execute(
            "SELECT COUNT(*) FROM ids WHERE source = ?", (expected_prefix,)
        ).fetchone()[0],
        "blank_address": address_blank,
        "countries": dict(sorted(countries.items())),
        "issues": dict(issues.counts),
        "examples": dict(issues.examples),
        "elapsed_seconds": round(time.perf_counter() - start, 2),
    }


def parse_match_list(raw: str) -> list[str] | None:
    if raw == "":
        return []
    values = raw.split(",")
    return values if all(value.strip() for value in values) else None


def validate_ground_truth(path: Path, conn: sqlite3.Connection) -> dict:
    issues = Issues()
    cardinality: Counter[int] = Counter()
    source_composition: Counter[str] = Counter()
    rows = 0
    start = time.perf_counter()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        require_columns(reader.fieldnames, EXPECTED_GT_COLUMNS, str(path))
        for row in reader:
            rows += 1
            s1 = row["source1_entity_id"]
            status = id_status(s1, "S1")
            if status:
                issues.add(f"ground_truth_{status}", s1 or "<blank>")
            elif conn.execute(
                "INSERT OR IGNORE INTO ground_truth_s1(entity_id, match_count) VALUES (?, 0)", (s1,)
            ).rowcount == 0:
                issues.add("duplicate_ground_truth_s1", s1)
            values = parse_match_list(row["matched_entity_ids"])
            if values is None:
                issues.add("malformed_or_empty_match_entry", s1)
                values = []
            if len(values) != len(set(values)):
                issues.add("duplicate_target_within_match_list", s1)
            targets = set(values)
            cardinality[len(targets)] += 1
            prefixes = {value.split("-", 1)[0] for value in targets if "-" in value}
            if prefixes == {"S2"}:
                source_composition["S2_only"] += 1
            elif prefixes == {"S3"}:
                source_composition["S3_only"] += 1
            elif prefixes == {"S2", "S3"}:
                source_composition["both"] += 1
            elif targets:
                source_composition["invalid_or_other"] += 1
            for target in targets:
                target_status = id_status(target, target.split("-", 1)[0] if "-" in target else "")
                if target.startswith("S1-"):
                    issues.add("s1_in_match_list", f"{s1}:{target}")
                elif target_status or not target.startswith(("S2-", "S3-")):
                    issues.add("malformed_or_unexpected_target", f"{s1}:{target}")
                else:
                    found = conn.execute("SELECT 1 FROM ids WHERE entity_id = ?", (target,)).fetchone()
                    if not found:
                        issues.add("unknown_target_reference", f"{s1}:{target}")
                    conn.execute(
                        "INSERT INTO target_reuse(entity_id, reference_count) VALUES (?, 1) "
                        "ON CONFLICT(entity_id) DO UPDATE SET reference_count = reference_count + 1",
                        (target,),
                    )
            if not status:
                conn.execute("UPDATE ground_truth_s1 SET match_count = ? WHERE entity_id = ?", (len(targets), s1))
    conn.commit()
    missing_s1 = conn.execute(
        "SELECT COUNT(*) FROM ground_truth_s1 gt LEFT JOIN ids s1 ON gt.entity_id=s1.entity_id "
        "WHERE s1.entity_id IS NULL"
    ).fetchone()[0]
    source1_count = conn.execute("SELECT COUNT(*) FROM ids WHERE source='S1'").fetchone()[0]
    gt_count = conn.execute("SELECT COUNT(*) FROM ground_truth_s1").fetchone()[0]
    reuse_counts = dict(conn.execute(
        "SELECT reference_count, COUNT(*) FROM target_reuse GROUP BY reference_count ORDER BY reference_count"
    ))
    reused = sum(count for n, count in reuse_counts.items() if n > 1)
    unique_referenced_targets = conn.execute("SELECT COUNT(*) FROM target_reuse").fetchone()[0]
    max_reuse = conn.execute("SELECT COALESCE(MAX(reference_count), 0) FROM target_reuse").fetchone()[0]
    return {
        "path": str(path), "rows": rows, "unique_ground_truth_s1": gt_count,
        "train_source1_unique_ids": source1_count,
        "ground_truth_row_count_matches_s1": rows == source1_count,
        "ground_truth_s1_missing_from_source1": missing_s1,
        "cardinality": dict(sorted(cardinality.items())),
        "zero_matches": cardinality[0], "one_match": cardinality[1],
        "multiple_matches": sum(v for k, v in cardinality.items() if k > 1),
        "source_composition": dict(sorted(source_composition.items())),
        "target_reuse": {"unique_referenced_targets": unique_referenced_targets, "targets_referenced_more_than_once": reused,
                         "maximum_s1_references_for_one_target": max_reuse,
                         "reference_count_histogram": reuse_counts},
        "issues": dict(issues.counts), "examples": dict(issues.examples),
        "elapsed_seconds": round(time.perf_counter() - start, 2),
    }


def gt_records(conn: sqlite3.Connection) -> Iterable[tuple[str, int]]:
    yield from conn.execute("SELECT entity_id, match_count FROM ground_truth_s1")


def create_split(conn: sqlite3.Connection, output_dir: Path, seed: int, fraction: float) -> dict:
    counts = Counter()
    for _, count in gt_records(conn):
        counts[count] += 1
    targets = validation_targets(counts, fraction)
    validation_ids = select_validation_ids(gt_records(conn), targets, seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    ids_path = output_dir / "validation_source1_ids.txt"
    ids_path.write_text("\n".join(sorted(validation_ids)) + "\n", encoding="utf-8")
    metadata = {
        "seed": seed, "validation_fraction": fraction, "selection": "stable_blake2b_rank_stratified_by_ground_truth_match_count",
        "validation_ids_file": str(ids_path), "training_definition": "all training Source-1 IDs not in validation_source1_ids.txt",
        "strata_total": dict(sorted(counts.items())), "strata_validation": dict(sorted(targets.items())),
        "validation_source1_count": len(validation_ids), "training_source1_count": sum(counts.values()) - len(validation_ids),
    }
    (output_dir / "split_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def markdown_report(result: dict) -> str:
    lines = ["# Data Validation Report", "", "## Result", "", f"- Status: **{result['status']}**", f"- Runtime: {result['elapsed_seconds']:.2f} seconds.",
        "- Peak Python-memory note: IDs were indexed in a temporary on-disk SQLite database; no full source TSV or multi-million-ID Python set was loaded.", "",
        "## Corrected row counts", "", "| File | Data rows (header excluded) |", "|---|---:|"]
    for name, item in result["sources"].items(): lines.append(f"| {name} | {item['rows']:,} |")
    lines.append(f"| train_ground_truth | {result['ground_truth']['rows']:,} |")
    lines += [f"| **Total seven TSV data rows** | **{result['total_data_rows']:,}** |", "",
        "Phase 0's 26,436,001 total was incorrect. The exact sum of data rows is 26,435,999. Adding one header for each of the seven TSVs gives 26,436,006 physical lines, so neither consistent convention produces 26,436,001.", "",
        "## Source-file validation", ""]
    for name, item in result["sources"].items():
        lines += [f"### {name}", "", f"- Rows / unique valid IDs: {item['rows']:,} / {item['unique_valid_ids']:,}.", f"- Countries: {item['countries']}.", f"- Blank address (allowed): {item['blank_address']:,}.", f"- Validation issue counts: {item['issues'] or 'none'}.", ""]
    gt = result["ground_truth"]
    lines += ["## Ground-truth integrity", "", f"- Rows match train S1: {gt['ground_truth_row_count_matches_s1']}; missing S1 references: {gt['ground_truth_s1_missing_from_source1']:,}.", f"- Match cardinality: {gt['cardinality']}.", f"- Zero / one / multiple: {gt['zero_matches']:,} / {gt['one_match']:,} / {gt['multiple_matches']:,}.", f"- Source composition: {gt['source_composition']}.", f"- Target-ID reuse: {gt['target_reuse']}.", f"- Validation issue counts: {gt['issues'] or 'none'}.", "",
        "## Reproducible S1 split", "", f"- Seed: {result['split']['seed']}; validation fraction: {result['split']['validation_fraction']:.0%}.", f"- Train / validation S1: {result['split']['training_source1_count']:,} / {result['split']['validation_source1_count']:,}.", f"- Stratified validation counts by ground-truth match count: {result['split']['strata_validation']}.", "",
        "## Test country statistics", ""]
    for name in ("test_source1", "test_source2", "test_source3"):
        item = result["sources"][name]
        lines.append(f"- {name}: France={item['countries'].get('France', 0):,}; all countries={item['countries']}.")
    return "\n".join(lines) + "\n"


def run_validation(data_root: Path, reports_dir: Path, seed: int = 2026, fraction: float = 0.10) -> dict:
    start = time.perf_counter()
    paths = {
        "train_source1": data_root / "train/train_source1.tsv", "train_source2": data_root / "train/train_source2.tsv", "train_source3": data_root / "train/train_source3.tsv",
        "test_source1": data_root / "test/test_source1.tsv", "test_source2": data_root / "test/test_source2.tsv", "test_source3": data_root / "test/test_source3.tsv",
    }
    with tempfile.TemporaryDirectory(prefix="ber_validation_") as temp_name:
        conn = open_database(Path(temp_name))
        try:
            sources = {name: validate_source(path, conn) for name, path in paths.items()}
            ground_truth = validate_ground_truth(data_root / "train/train_ground_truth.tsv", conn)
            split = create_split(conn, reports_dir / "splits", seed, fraction)
        finally:
            conn.close()
    total = sum(item["rows"] for item in sources.values()) + ground_truth["rows"]
    failures = sum(sum(item["issues"].values()) for item in sources.values()) + sum(ground_truth["issues"].values()) + ground_truth["ground_truth_s1_missing_from_source1"]
    result = {"status": "PASS" if not failures else "FAIL", "sources": sources, "ground_truth": ground_truth, "split": split,
              "total_data_rows": total, "elapsed_seconds": time.perf_counter() - start}
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "data_validation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (reports_dir / "data_validation.md").write_text(markdown_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("dataset"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--validation-fraction", type=float, default=0.10)
    args = parser.parse_args()
    result = run_validation(args.data_root, args.reports_dir, args.seed, args.validation_fraction)
    print(f"{result['status']}: {result['total_data_rows']:,} data rows in {result['elapsed_seconds']:.2f}s")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
