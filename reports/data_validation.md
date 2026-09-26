# Data Validation Report

## PHASE 1 — STOPPED / PARTIALLY COMPLETED

Phase 1 was stopped at the user's direction before the exhaustive full-corpus
validation job completed. No Phase 2 work was started.

## Completed checks

- Implemented streaming source/ground-truth validation in
  `code/business_entity_resolution/src/data_validation.py`, using a temporary
  SQLite index rather than loading all IDs or TSVs into memory.
- Implemented deterministic, Source-1-level, match-count-stratified split logic
  in `code/business_entity_resolution/src/split.py`. It uses seed `2026` and a
  10% validation fraction; training is defined as the complement of the compact
  validation-ID list.
- Added and ran five synthetic unit tests successfully: malformed/missing ID,
  duplicate ID, invalid ground-truth reference, S1 self-match, duplicate IDs in a
  match list, deterministic split, and train/validation disjointness.
- Reconciled Phase 0 row counts from already-completed `wc -l` measurements:
  the seven files contain **26,435,999 data rows** (headers excluded). Including
  all seven headers gives 26,436,006 physical lines. The prior 26,436,001 figure
  is not produced by either consistent convention.
- Previously observed country/missingness statistics remain available in
  `decision_log.md`: test contains France; S2/S3 may have blank addresses.

## Incomplete checks

- The exhaustive full-data validation run was interrupted before it produced its
  final report or split artifacts. Therefore no final pass/fail result is
  available for source-ID uniqueness/prefix checks, ground-truth target existence,
  S1 membership, target reuse, or split sizes on the real corpus.
- `reports/splits/` was not produced by the interrupted run and must not be
  treated as available validation output.

## Runtime and memory observations

- The interrupted full audit ran for roughly 40 minutes before being stopped.
- Observed Python RSS stayed approximately 11–14 MB. The temporary SQLite index
  grew to roughly 1.4 GB on disk and was designed to be removed when the run
  exits; no source TSV copies were created.

## Risks

- Do not claim full input or reference integrity until the exhaustive validation
  is rerun to completion.
- The current per-reference SQLite implementation is memory-safe but slow on the
  local M1 machine; optimize/batch it before a future rerun if runtime is a
  concern, while retaining exact checks.
