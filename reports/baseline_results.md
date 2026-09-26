# Phase 4 Deterministic Baseline Results

```json
{
  "coverage": {
    "candidate_coverage_percentage": 69.93696841170366,
    "validation_s1_with_candidate": 154339,
    "validation_s1_zero_candidates": 66344
  },
  "examples": {
    "false_negative_examples": [
      "S1-100003745: missed=1, predicted=2, true=3",
      "S1-100003832: missed=4, predicted=0, true=4",
      "S1-100008028: missed=1, predicted=15, true=2",
      "S1-100020950: missed=4, predicted=1, true=5",
      "S1-100023796: missed=3, predicted=1, true=4"
    ],
    "false_positive_examples": [
      "S1-100008028: false_positive=14, predicted=15, true=2",
      "S1-100025870: false_positive=12, predicted=12, true=1",
      "S1-100033015: false_positive=7, predicted=7, true=7",
      "S1-100092692: false_positive=1, predicted=1, true=4",
      "S1-10011925: false_positive=3, predicted=5, true=4"
    ]
  },
  "metrics": {
    "average_predicted_matches_per_s1": 5.860854710149853,
    "evaluated_source1_count": 220683,
    "macro_f05": 0.33520521963554367,
    "macro_precision": 0.4290202351814718,
    "macro_recall": 0.24836071252074507,
    "singleton_accuracy": 0.6550912778904665,
    "singleton_count": 12325,
    "singleton_false_positive_rate": 0.3449087221095335
  },
  "peak_rss_bytes": 705249280,
  "prediction_statistics": {
    "average_predicted_matches_per_s1": 5.860854710149853,
    "median_predicted_matches_per_s1": 1,
    "multiple_prediction_percentage": 44.87296257527766,
    "no_prediction_percentage": 30.063031588296333,
    "one_prediction_percentage": 25.064005836426006,
    "suppressed_ambiguous_s1": 4985
  },
  "timings": {
    "s1_index_seconds": 9.296045875002164,
    "s2_rows": 5034616,
    "s3_rows": 5285603,
    "target_scan_seconds": 202.8763787499629,
    "total_seconds": 217.24578983400716
  }
}
```

## Interpretation

### Method

- Validation S1 records were normalized and indexed by `(normalized_country,
  normalized_name)`, `(country, core_name)`, and `(country, sorted_tokens)`.
- S2 and S3 were streamed separately once. A target was predicted for all matching
  S1 records under either: (a) exact normalized name and country, or (b) exact core
  name or sorted tokens, country, and exact non-empty compact-address agreement.
- Candidate lists are sets, so S2 and S3 matches are combined and multiple matches
  are retained. An ambiguity guard suppresses an S1 after more than 100 candidates
  rather than silently truncating its list; this affected 4,985 S1 records.
- This is indexed lookup only—no all-pairs fuzzy comparison and no candidate-pair
  file was created.

### Failure patterns

- False negatives are dominated by name/address variants that fail exact forms,
  incomplete source records, and true one-to-many links where only a subset shares
  an exact representation. For example, `S1-100003832` had four true links and no
  baseline prediction.
- False positives occur for non-unique names despite country agreement; for example,
  `S1-100008028` received 15 predictions for two true links, with 14 false positives.
  This explains the precision-heavy F0.5 limitation and poor singleton behavior.
- The next blocking phase should retain recall-oriented multi-key candidates but add
  frequency controls and a later scoring/thresholding stage to reject ambiguous
  common-name collisions.

### Runtime and memory

- Sample gate: 50,000 rows from each target source completed in 15.95 seconds
  (including the S1 scan), with roughly 659 MiB peak RSS.
- Full run: S1 index 9.30 seconds; target scans 202.88 seconds; total 217.25
  seconds (3.62 minutes). `/usr/bin/time -l` measured maximum resident set size
  795,918,336 bytes (about 759 MiB); no swapping was reported.
