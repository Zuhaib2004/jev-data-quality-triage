PRAGMA foreign_keys = ON;
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    policy_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    threshold REAL NOT NULL CHECK (threshold BETWEEN 0 AND 1),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE decisions (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    record_id TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('ACCEPT','REPAIR','QUARANTINE')),
    source TEXT NOT NULL,
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    original_json TEXT NOT NULL CHECK (json_valid(original_json)),
    validated_json TEXT CHECK (validated_json IS NULL OR json_valid(validated_json)),
    audit_json TEXT NOT NULL CHECK (json_valid(audit_json)),
    PRIMARY KEY (run_id, row_number),
    CHECK ((decision = 'QUARANTINE' AND validated_json IS NULL)
        OR (decision <> 'QUARANTINE' AND validated_json IS NOT NULL))
);
CREATE VIEW validated_records AS
SELECT run_id, row_number, record_id, decision, validated_json
FROM decisions WHERE decision IN ('ACCEPT','REPAIR');
CREATE VIEW rejected_records AS
SELECT run_id, row_number, record_id, original_json, audit_json
FROM decisions WHERE decision = 'QUARANTINE';
CREATE INDEX decisions_by_route ON decisions(decision, source);
