# Phase 5 Blocking Analysis

## Selected validation-only candidate generator

The generator streams S2 and S3 separately and uses validation-S1 inverted indexes;
it never creates S1×target comparisons or S2×S3 candidates. Candidate metadata is
an internal per-pair bit mask of the rule(s) that emitted it. It is not written as a
candidate-pair dump in this phase.

Selected union: exact normalized name, core name, sorted-token name, postal/PIN-like
token, and name-token + address-number. Every key includes the open-set normalized
country. Standalone rare-token and name-prefix passes were measured but rejected:
the bounded benchmark showed large candidate growth for small incremental recovery.

## Key frequency controls

Frequency caps were the empirical P95 target frequency among only keys shared with
validation S1, separately per representation: exact=15, core=44, sorted=17,
postal=559, name-number=67. Keys above their representation cap emit no candidates.
See `blocking_key_statistics.csv` for the measured tail distributions; for example,
rare-token had max frequency 1,199,657 and name-number had max 106,349, so neither
is allowed to form unrestricted products.

## Full validation results

- True validation links: 763,837; candidates recovered: 550,721.
- S2 recall: 0.709300 (261,953 / 369,312).
- S3 recall: 0.731938 (288,768 / 394,525).
- Combined blocking recall: **0.720993**; missed true links: 213,116.
- Candidate pairs: 17,151,554, versus 2,277,496,889,577 all pairs; reduction ratio:
  **0.9999924691** (the candidate set is ~0.000752% of all pairs).
- Candidates/S1: mean 77.720, median 27, P90 254, P95 385, P99 529, maximum 1,520.
- Zero-candidate S1: 4,685 (2.123%).

## Ablation and trade-offs

The exact measured per-rule values are in `blocking_rule_results.csv`; configuration
comparisons are in `blocking_experiments.csv`.

- Exact name alone is compact (452,718 events) but recalls only 18.90% of true links.
- Core name has 34.44% standalone recall and 4.10 percentage points unique recovery
  in the selected union.
- Name-token + address-number is the strongest pass: 58.91% standalone recall and
  22.38 percentage points unique union recovery.
- Postal adds 12.16M rule events for only 2.38 percentage points unique recovery.
  It is retained in this high-recall validation configuration, but is the first
  candidate for removal or stricter capping in a balanced future configuration.

## Runtime and memory

- The bounded 10k-S1 / 50k-per-source benchmark completed in 12.33 seconds with
  116,473,856-byte peak RSS (~111 MiB).
- The full run took 687.57 seconds (11.46 minutes): two frequency scans plus two
  capped candidate scans, with 500k-row progress reports throughout.
- Maximum resident set size was 1,574,109,184 bytes (~1.47 GiB); `/usr/bin/time`
  reported no swaps and a 2,039,436,416-byte peak memory footprint (~1.90 GiB).

## Failure patterns and risks

- True links are missed when country differs/noises, no normalized name token or
  number agrees, no postal token is available, or a needed key falls in the capped
  high-frequency tail.
- Postal and address-number keys can still create high fan-out; 1,520 candidates
  is the observed maximum. A later precision matcher and per-source/model batching
  are necessary before using all candidates for inference.
- The deferred Phase 1 source/reference audit remains unresolved; pair construction
  and final output must re-enforce applicable ID integrity checks.
