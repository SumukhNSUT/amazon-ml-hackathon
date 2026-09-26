# Phase 4 Deterministic Baseline Results

```json
{
  "coverage": {
    "candidate_coverage_percentage": 6.492570791587934,
    "validation_s1_with_candidate": 14328,
    "validation_s1_zero_candidates": 206355
  },
  "examples": {
    "false_negative_examples": [
      "S1-100003745: missed=3, predicted=0, true=3",
      "S1-100003832: missed=4, predicted=0, true=4",
      "S1-100008028: missed=2, predicted=0, true=2",
      "S1-100020950: missed=5, predicted=0, true=5",
      "S1-100023796: missed=4, predicted=0, true=4"
    ],
    "false_positive_examples": [
      "S1-100133916: false_positive=1, predicted=1, true=3",
      "S1-100155508: false_positive=3, predicted=3, true=3",
      "S1-100173753: false_positive=1, predicted=1, true=1",
      "S1-100256533: false_positive=2, predicted=2, true=4",
      "S1-1002709: false_positive=2, predicted=2, true=2"
    ]
  },
  "metrics": {
    "average_predicted_matches_per_s1": 0.09353688322163466,
    "evaluated_source1_count": 220683,
    "macro_f05": 0.057125932477705456,
    "macro_precision": 0.05977710864301587,
    "macro_recall": 0.05463141717338948,
    "singleton_accuracy": 0.9415821501014199,
    "singleton_count": 12325,
    "singleton_false_positive_rate": 0.05841784989858012
  },
  "peak_rss_bytes": 689537024,
  "prediction_statistics": {
    "average_predicted_matches_per_s1": 0.09353688322163466,
    "median_predicted_matches_per_s1": 0,
    "multiple_prediction_percentage": 1.8148203531762754,
    "no_prediction_percentage": 93.50742920841206,
    "one_prediction_percentage": 4.677750438411659,
    "suppressed_ambiguous_s1": 0
  },
  "timings": {
    "s1_index_seconds": 9.120666624978185,
    "s2_rows": 50000,
    "s3_rows": 50000,
    "target_scan_seconds": 2.0341735419933684,
    "total_seconds": 15.94989704200998
  }
}
```
