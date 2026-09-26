# Decision Log

## Phase 0 — Repository and data discovery (2026-09-26)

### Observations

- This workspace is a challenge data drop with `README.md`, the supplied validator,
  the documentation template, and the seven TSV inputs. It has no existing source
  pipeline and is not currently a Git working tree.
- The training row counts are: S1 2,206,821; S2 5,034,617; S3 5,285,604; ground
  truth 2,206,821. The test row counts are: S1 1,732,545; S2 4,887,274; S3
  5,082,317.
- Training countries are `India` and `US`. Test also contains `France`: S1 259,452,
  S2 703,378, S3 731,615 rows. Country must remain an open string field.
- All source records have a non-empty business name and country. Address is missing
  in S2/S3 (training: 168,967 / 175,916; test: 129,408 / 136,098), while S1
  addresses are complete in both splits.
- Ground truth contains 7,638,365 links. Per-S1 label cardinality is: 0=123,247,
  1=119,157, 2=375,212, 3=530,841, 4=484,115, 5=321,957, 6=164,868, 7=63,968,
  8=18,680, 9=4,205, 10=534, 11=37.

### Decisions

- Use a modular, streaming/indexed candidate-generation design. The 26,436,001
  total TSV rows and an 8 GB development machine rule out all-pairs comparison and
  dense feature matrices.
- Preserve country as an unmodified, generic blocking/comparison field; never
  restrict the implementation to the training-country vocabulary.
- Treat name-only matching as a required fallback path because a material share of
  S2/S3 addresses are missing.
- Keep the supplied `utils/validate_submission.py` unchanged. Its `--check-ids`
  mode is explicitly a high-memory diagnostic, so routine local validation should
  use the default mode unless sufficient memory is available.

### Alternatives deferred

- Learned matching models, embedding retrieval, and graph methods are deferred
  until a baseline split, blocking-recall measurement, and error analysis justify
  them.
- No data files or original challenge utilities were modified in this phase.

### Risks / assumptions

- Row-count alignment between training S1 and ground truth has been established;
  exact ID-set and duplicate checks should be part of the first data-validation
  module rather than relying on row counts alone.
- The provided source files occupy about 2.4 GB, so later experiments must measure
  peak memory and avoid simultaneous full-table loads.

## PHASE 1 — STOPPED / PARTIALLY COMPLETED (2026-09-26)

### Completed

- Added modular, streaming validation and deterministic S1-level split code under
  `code/business_entity_resolution/src/`, plus five synthetic unit tests. All five
  tests passed.
- Reconciled the Phase 0 count discrepancy: 26,435,999 is the exact total number
  of data rows across the seven TSVs; counting all seven headers gives 26,436,006
  physical lines. The earlier 26,436,001 figure was erroneous.
- The proposed split is seed 2026, 10%, stratified by complete S1 ground-truth
  match count, with training defined as the complement of compact validation IDs.

### Stopped / incomplete

- The exhaustive source and ground-truth audit was explicitly stopped before it
  completed. Its final report and real-corpus split artefacts were not produced.
- Consequently, do not treat duplicate/prefix/reference/reuse checks or real split
  sizes as verified. No Phase 2 work was started.

### Runtime and risk

- The interrupted disk-indexed audit ran for about 40 minutes with observed Python
  RSS around 11–14 MB and a temporary SQLite index reaching about 1.4 GB.
- The approach is memory-safe for the 8 GB machine but needs batching or other
  performance work before a future exhaustive rerun. Preserve exact membership
  validation; do not replace it with a sampled assertion.

### Decision: exhaustive audit deferred

- Phase 1 basic profiling and validation work was completed. The remaining exact
  ID/reference audit was intentionally deferred because of its runtime cost on the
  26M+ row dataset and 8 GB RAM development environment.
- This deferral does **not** assume the data is perfectly clean. Critical integrity
  checks must still be enforced when constructing training pairs and final
  submission outputs.

## Phase 2 — Conservative text normalization (2026-09-26)

### Decisions

- Use stdlib-only NFKC Unicode normalization, case-folding, conservative punctuation
  cleanup, and whitespace collapsing. Preserve non-Latin scripts; do not use
  transliteration libraries or external data.
- Keep multiple name forms: full normalized tokens, joined alphanumeric form,
  legal-suffix-stripped core name, and sorted tokens. Legal suffixes are removed
  only from the core form, retaining the complete representation for later checks.
- Addresses retain normalized tokens, compact form, numeric tokens, and a broad
  postal/PIN/ZIP-like extractor. Country stays an open normalized string plus a
  missing flag; no country vocabulary is hard-coded.

### Alternatives deferred

- Aggressive abbreviation expansion, transliteration, address parsing, geocoding,
  and learned normalization are deferred: they need measured validation benefit and
  could create false equivalences.

### Benchmark and limitations

- A bounded, streaming 10,000-row sample from `train_source1.tsv` completed in
  0.2553 seconds (39,177 rows/second) on the local machine. Normalized records were
  discarded immediately; no full normalized dataset or DataFrame was materialized.
- The Phase 1 exhaustive ID/reference audit remains intentionally deferred. Future
  training-pair construction and final-output generation must enforce their own
  relevant integrity checks rather than relying on an assumption of clean inputs.

## Phase 3 — Ground truth, deterministic split, and evaluator (2026-09-26)

### Results

- Added a streaming ground-truth parser, compact real S1-level train/validation
  split writer, and exact macro F0.5 evaluator. The split reads only
  `train_ground_truth.tsv`, not the 26M+ source corpus.
- With fixed seed 2026 and match-count stratification, the split contains 1,986,138
  train S1 entities and 220,683 validation S1 entities; measured overlap is zero.
- No large source TSV was copied. The real split completed in 15.58 seconds with
  peak resident memory of 78,757,888 bytes (about 75.1 MiB).
- All 17 project tests pass, including empty/single/multiple/both-source labels,
  singleton scoring, deterministic split/disjointness, and the challenge F0.5
  example (0.7142857143).

### Decision rationale and remaining risk

- Splitting at the S1 entity level preserves every complete match set and prevents
  label leakage from individual links. Stratification by complete match-count keeps
  the dominant multi-match and important singleton populations aligned across
  train/validation.
- The deferred Phase 1 source/reference audit remains a limitation: this framework
  assumes only the provided ground-truth row structure, not independently verified
  source-target existence. Enforce integrity again when building pairs and outputs.

## Phase 4 — Deterministic exact-match baseline (2026-09-26)

### Rules and rationale

- Indexed only validation S1 normalized representations, then streamed S2 and S3
  separately once. The baseline predicts every target satisfying either exact
  normalized name + country, or exact core/sorted name + country + exact non-empty
  compact address. This is deterministic, interpretable, supports multiple matches,
  and uses no all-pairs comparison.
- Country is an open normalized string. The address requirement for broadened
  core/sorted name matching is a conservative precision support; full exact name is
  allowed without address because target addresses are sometimes missing.
- An explicit ambiguity guard suppresses lists exceeding 100 candidates rather than
  silently truncating them; 4,985 validation S1 records were suppressed.

### Measured validation result

- Macro precision 0.429020; recall 0.248361; F0.5 0.335205.
- Singleton accuracy 0.655091; singleton false-positive rate 0.344909.
- Candidate coverage was 69.936968% (154,339 / 220,683); 66,344 had no candidates.
  Average predictions/S1 was 5.860855; median 1; zero/one/multiple prediction rates
  were 30.063032% / 25.064006% / 44.872963%.
- The 50k-per-target sample completed in 15.95 seconds. Full validation completed
  in 217.25 seconds: 9.30 seconds S1 indexing plus 202.88 seconds target scans.
  `/usr/bin/time -l` reported 795,918,336-byte maximum RSS (~759 MiB), no swaps.

### Weaknesses and Phase 5 implication

- Exact forms miss noisy, abbreviated, reordered, partial, and otherwise divergent
  records, causing recall loss and incomplete one-to-many recovery.
- Common names create false candidates even with country agreement: examples include
  an S1 with 15 predicted IDs for two true IDs. This also produces false positives
  on singleton entities.
- Phase 5 should develop recall-oriented multi-key blocking with per-key frequency
  controls and measured candidate recall, preserving candidates for a later matcher
  instead of treating this baseline's exact rules as a final decision rule.

## Phase 5 — Multi-pass validation blocking (2026-09-26)

### Evidence and selected design

- Full validation S1-relevant frequency scans measured P95 target-key frequencies:
  exact name 15, core name 44, sorted name 17, postal 559, and name+number 67.
  These empirical thresholds cap high-frequency Cartesian effects without any
  country vocabulary assumptions. The complete distributions are recorded in
  `reports/blocking_key_statistics.csv`.
- The selected union is exact name, core name, sorted name, postal, and name-token
  plus address-number. All keys include normalized open-set country. It streams S2
  and S3 independently, keeps deduplicated per-S1 target candidates and rule masks,
  and never does all-pairs or S2-S3 matching.
- Standalone rare-token and name-prefix rules were considered and measured. The
  bounded benchmark showed high candidate growth for small unique recovery, so they
  are not retained in the full candidate union.

### Measured result

- Combined blocking recall is 0.720993 (550,721 / 763,837): S2 0.709300 and S3
  0.731938. The union has 17,151,554 pairs, 77.720 per S1 on average (median 27;
  P95 385), 2.123% zero-candidate S1, and a 0.9999924691 reduction ratio against
  2,277,496,889,577 all pairs.
- Exact/core/sorted/postal/name-number unique recall contributions are 0.000850 /
  0.041021 / 0.006601 / 0.023822 / 0.223765. Name+number is the key recall pass.
  Postal produced 12.16M rule events for only 2.38 unique recall points, making it
  the leading candidate for stricter future balancing.
- Full two-frequency-plus-two-candidate scan runtime was 687.57 seconds; maximum
  resident set size was 1.47 GiB (1.90 GiB peak memory footprint), with zero swaps.

### Risks and next implication

- 72.1% recall is a defensible scalable starting point but not sufficient as a final
  recall ceiling. Misses arise from divergent names/addresses, missing tokens, and
  intentionally suppressed high-frequency keys.
- Candidate volume and high postal fan-out require later chunked matching and
  precision scoring. Do not emit final test candidate files until the selected
  blocking trade-off is validated with the matcher.
