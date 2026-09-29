-- sqlite3 runs/<run-id>/audit.sqlite < sql/quality_report.sql
.headers on
.mode column
SELECT decision, source, COUNT(*) AS records, ROUND(AVG(confidence), 3) AS avg_confidence
FROM decisions GROUP BY decision, source ORDER BY decision, source;

SELECT json_extract(f.value, '$.code') AS finding, COUNT(*) AS occurrences
FROM decisions AS d, json_each(d.audit_json, '$.findings') AS f
GROUP BY finding ORDER BY occurrences DESC;

SELECT row_number, record_id, json_extract(audit_json, '$.reasons') AS review_reasons
FROM rejected_records ORDER BY row_number;
