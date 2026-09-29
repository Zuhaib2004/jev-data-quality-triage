import hashlib
import json
import shutil
import sqlite3
import tempfile
import uuid
from importlib.resources import files
from pathlib import Path

from .io import records
from .models import Decision
from .pipeline import triage
from .rules import POLICY_VERSION


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def run(input_path, output_root, provider=None, threshold=0.85):
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between zero and one")
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=output_root))
    final = output_root / run_id
    counts = {d.value: 0 for d in Decision}
    try:
        with sqlite3.connect(stage / "audit.sqlite") as db:
            db.executescript(files("jev_triage").joinpath("schema.sql").read_text())
            db.execute("INSERT INTO runs(run_id,policy_version,provider,threshold) VALUES(?,?,?,?)",
                       (run_id, POLICY_VERSION, "jev" if provider else "offline", threshold))
            with (stage / "validated.jsonl").open("w", encoding="utf-8") as accepted, \
                 (stage / "rejected.jsonl").open("w", encoding="utf-8") as rejected, \
                 (stage / "decisions.jsonl").open("w", encoding="utf-8") as audit:
                seen = set()
                digest = hashlib.sha256()
                for row, record in enumerate(records(input_path), 1):
                    digest.update((encode(record) + "\n").encode())
                    outcome = triage(record, row, seen, provider, threshold)
                    data = outcome.to_dict()
                    counts[outcome.decision.value] += 1
                    audit.write(encode(data) + "\n")
                    if outcome.decision == Decision.QUARANTINE:
                        rejected.write(encode(data) + "\n")
                    else:
                        accepted.write(encode(outcome.record) + "\n")
                    record_id = outcome.original.get("record_id")
                    db.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?)", (
                        run_id, row, record_id if isinstance(record_id, str) else None,
                        outcome.decision.value, outcome.source, outcome.confidence,
                        encode(outcome.original),
                        encode(outcome.record) if outcome.record is not None else None, encode(data),
                    ))
            summary = {"run_id": run_id, "policy_version": POLICY_VERSION,
                       "provider": "jev" if provider else "offline", "threshold": threshold,
                       "counts": counts, "total": sum(counts.values()),
                       "parsed_input_sha256": digest.hexdigest()}
            (stage / "summary.json").write_text(encode(summary) + "\n", encoding="utf-8")
        # A run is visible only when all outputs and the database transaction are complete.
        db.close()
        stage.rename(final)
        return final, summary
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        if "db" in locals():
            db.close()
