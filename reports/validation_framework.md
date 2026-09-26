# Validation Framework Report

## Phase 3 — Ground truth, S1 split, and exact macro F0.5

## Measured split output

- Ground-truth S1 records: **2,206,821**.
- Seed: **2026**.
- Selection: stable BLAKE2b rank, stratified by each S1 entity's complete
  ground-truth match-count.
- Train S1: **1,986,138** (90.0000%).
- Validation S1: **220,683** (10.0000%).
- Train/validation overlap: **0**; union: **2,206,821**.
- Only compact S1 ID files and JSON metadata were written in `reports/splits/`.
  No source TSV was copied or read during the split.

| Match-count group | Train | Validation |
|---|---:|---:|
| Singleton / no match (0) | 110,922 (5.585%) | 12,325 (5.585%) |
| Exactly one match | 107,241 (5.400%) | 11,916 (5.400%) |
| Multiple matches (2+) | 1,767,975 (89.015%) | 196,442 (89.015%) |

The full per-match-count distributions are in
`reports/splits/split_metadata.json`.

## Evaluator behavior

- Scores complete predicted and true S2/S3 ID sets per S1, then macro-averages
  precision, recall, and F0.5.
- A true empty set with an empty prediction scores 1.0; a true empty set with a
  prediction scores 0.0.
- Also reports singleton accuracy, singleton false-positive rate, and average
  predicted matches per S1.

## Tests and runtime

- Full unit suite: **17 passed**.
- F0.5 challenge example passed: precision=2/3, recall=1, F0.5=0.7142857143.
- Real ground-truth-only split runtime: **15.58 seconds**; peak resident memory:
  **78,757,888 bytes** (about 75.1 MiB, as measured by `/usr/bin/time -l`).

## Limitation carried from Phase 1

The exhaustive source-ID and target-reference audit remains intentionally deferred;
this split validates neither source-file existence nor target-ID validity. Pair
construction and final submission output must enforce the relevant integrity checks.
