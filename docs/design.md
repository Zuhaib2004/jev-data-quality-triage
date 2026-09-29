# Design decisions

## Policy has the final word

The pipeline first builds a canonical candidate and an explicit change set without mutating the original. A hard contract violation always quarantines the record. Clean or deterministically repairable records bypass Jev completely. Only an unusual valid age or non-empty notes triggers the optional provider.

Jev returns two independent choices. Both confidences must meet the configured threshold. An adverse reason always forces review even if the decision says ACCEPT. A REPAIR choice requires an existing local change set. No generated replacement strings are accepted. Every accepted candidate is checked again against the hard contract before writing.

## Two confidence meanings are deliberately visible

Rule confidence 1.0 describes policy application, not world truth. Model confidence is an upstream quantity derived from a distribution; it is retained together with the probabilities. Error and offline-fallback routes use null, never an invented score. Model reason confidence is also retained. A consumer must group by `source` rather than comparing these as one calibrated metric.

## Transport and response boundaries

The client uses the official REST endpoint directly, with a fixed HTTPS destination and no redirects. It validates Choice labels, answer type, all probability keys, numeric bounds, probability sum (0.01 tolerance), argmax consistency, and non-empty returned model name. Request timeout is 20 seconds. Transport failures, 429, 529, and selected 5xx statuses allow at most three attempts. Numeric Retry-After values are capped at eight seconds; malformed/date-valued headers fail closed. Authentication and malformed responses do not retry.

The application never logs API keys, request payloads, or raw error responses. Invalid response structure becomes a generic provider-failure reason. Dependency or programming errors outside this defined failure contract abort the run; they are not disguised as model judgments.

## Data boundaries

Only age, country, status, notes, soft rule findings, and names of normalization fields are transmitted. IDs and emails are omitted. This is minimization, not anonymization: free-text notes can contain sensitive information. The explicit `--allow-ai-data` flag acknowledges that boundary. Use approved datasets and the appropriate provider agreement for real deployments.

Local JSONL and SQLite files retain original records and therefore may contain personal information. Storage access control, encryption, retention and deletion policies belong to the deployment environment; they are not provided by this CLI. No production records or credentials are committed.

## Input and output integrity

Duplicate JSON keys, NaN/Infinity literals, malformed CSV structure, and non-object records reject the input run. Missing/invalid business values within a structurally valid record produce a record-level quarantine. IDs are normalized before duplicate detection; the first occurrence reserves the ID even if it is later quarantined.

Output is first written to a hidden staging directory. SQLite commits before an atomic directory rename exposes the run. The CLI removes staging output after ordinary exceptions and interrupts. Hard process termination can leave an unpublished `.pending-*` directory; operators may remove it after checking no job is using it. Atomic publication is not a filesystem durability guarantee: there is no fsync or distributed transaction.

Each invocation gets a new run ID. Repeated invocations do not overwrite previous runs but can repeat external inference charges. The input fingerprint hashes parsed records in input order; it is not a checksum of original file bytes.

## Evaluation before production

Create a held-out labeled dataset containing legitimate centenarians, notes/status contradictions, harmless free text, typos, and malicious instructions embedded in notes. Measure false acceptance and unnecessary quarantine separately. Evaluate confidence thresholds by source and reason. Capture model versions, prompt/policy changes, and representative failure cases. The default 0.85 threshold is a starting policy, not empirically validated calibration.

This reference implementation has no ground-truth accuracy claim and no live Jev smoke test in CI. Provider contract tests are mocked; running the real integration requires a TypeSafe key.
