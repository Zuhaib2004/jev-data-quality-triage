import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jev_triage.io import InputError, records
from jev_triage.jev import JevError
from jev_triage.models import Decision, Verdict
from jev_triage.pipeline import triage
from jev_triage.runner import run


def good(**kwargs):
    return dict(record_id="c1", email="Ada@example.com", age=30,
                country="US", status="active", **kwargs)


def verdict(decision=Decision.ACCEPT, confidence=0.98, reason="CONSISTENT"):
    return Verdict(decision, confidence, {d.value: float(d == decision) for d in Decision},
                   reason, 0.98, "jev-test")


class PipelineTests(unittest.TestCase):
    def test_clean_accept_never_calls_ai(self):
        ai = Mock()
        out = triage(good(), provider=ai)
        self.assertEqual(out.decision, Decision.ACCEPT)
        self.assertEqual(out.confidence, 1.0)
        ai.decide.assert_not_called()

    def test_safe_repairs_preserve_original(self):
        row = good()
        row.update(age="030", country="uk", email=" Ada@EXAMPLE.COM ", status="ACTIVE")
        out = triage(row)
        self.assertEqual(out.decision, Decision.REPAIR)
        self.assertEqual(out.record["email"], "Ada@example.com")
        self.assertEqual(out.record["age"], 30)
        self.assertEqual(out.record["country"], "GB")
        self.assertEqual(out.original, row)
        self.assertEqual(row["age"], "030")

    def test_hard_failures_cannot_be_overridden(self):
        cases = [("email", None), ("age", True), ("age", -1), ("age", 121),
                 ("age", "3.4"), ("age", {}), ("country", "ZZ"), ("status", "deleted"),
                 ("email", "bad"), ("record_id", []), ("notes", {}), ("notes", "x" * 2001)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                row = good()
                row[key] = value
                ai = Mock()
                self.assertEqual(triage(row, provider=ai).decision, Decision.QUARANTINE)
                ai.decide.assert_not_called()

    def test_duplicate_ids(self):
        seen = set()
        self.assertEqual(triage(good(), seen=seen).decision, Decision.ACCEPT)
        self.assertEqual(triage(good(), seen=seen).decision, Decision.QUARANTINE)

    def test_unknown_fields(self):
        self.assertEqual(triage(good(extra="no")).decision, Decision.QUARANTINE)

    def test_offline_ambiguity(self):
        out = triage(good(notes="Possibly closed"))
        self.assertEqual(out.decision, Decision.QUARANTINE)
        self.assertIsNone(out.confidence)
        self.assertEqual(out.source, "offline_fallback")

    def test_high_confidence_accept(self):
        ai = Mock(decide=Mock(return_value=verdict()))
        out = triage(good(notes="Customer confirmed active"), provider=ai)
        self.assertEqual(out.decision, Decision.ACCEPT)
        self.assertEqual(out.model_verdict.model, "jev-test")

    def test_low_confidence_quarantine(self):
        ai = Mock(decide=Mock(return_value=verdict(confidence=0.3)))
        out = triage(good(notes="unclear"), provider=ai)
        self.assertEqual(out.decision, Decision.QUARANTINE)
        self.assertEqual(out.confidence, 0.3)

    def test_low_reason_confidence_quarantine(self):
        v = verdict()
        v.reason_confidence = 0.2
        out = triage(good(notes="unclear"), provider=Mock(decide=Mock(return_value=v)))
        self.assertEqual(out.decision, Decision.QUARANTINE)

    def test_adverse_reason_overrides_accept(self):
        ai = Mock(decide=Mock(return_value=verdict(reason="CONTRADICTION")))
        self.assertEqual(triage(good(notes="closed"), provider=ai).decision, Decision.QUARANTINE)

    def test_ai_cannot_invent_repairs(self):
        ai = Mock(decide=Mock(return_value=verdict(Decision.REPAIR)))
        self.assertEqual(triage(good(notes="unclear"), provider=ai).decision, Decision.QUARANTINE)

    def test_ai_repair_with_allowlisted_change(self):
        row = good(notes="active")
        row["country"] = "USA"
        ai = Mock(decide=Mock(return_value=verdict(Decision.REPAIR, reason="SAFE_NORMALIZATION")))
        out = triage(row, provider=ai)
        self.assertEqual(out.decision, Decision.REPAIR)
        self.assertEqual(out.record["country"], "US")

    def test_ai_accept_with_changes_is_reported_as_repair(self):
        row = good(notes="active")
        row["country"] = "USA"
        out = triage(row, provider=Mock(decide=Mock(return_value=verdict())))
        self.assertEqual(out.decision, Decision.REPAIR)

    def test_provider_failure(self):
        ai = Mock(decide=Mock(side_effect=JevError("JEV_TRANSPORT_FAILURE")))
        out = triage(good(notes="unclear"), provider=ai)
        self.assertEqual(out.source, "provider_fallback")
        self.assertEqual(out.decision, Decision.QUARANTINE)
        self.assertIsNone(out.confidence)

    def test_invalid_threshold(self):
        for threshold in [-1, 2, float("nan")]:
            with self.assertRaises(ValueError):
                triage(good(), threshold=threshold)


class IOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text, suffix=".json"):
        path = self.root / ("input" + suffix)
        path.write_text(text)
        return path

    def test_json_roundtrip_and_sql_views(self):
        bad = good()
        bad["email"] = None
        path = self.write(json.dumps([good(), bad]))
        output, summary = run(path, self.root / "runs")
        self.assertEqual(summary["total"], 2)
        self.assertEqual(len((output / "validated.jsonl").read_text().splitlines()), 1)
        self.assertEqual(len((output / "rejected.jsonl").read_text().splitlines()), 1)
        with closing(sqlite3.connect(output / "audit.sqlite")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM validated_records").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM rejected_records").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE decisions SET decision='INVALID'")

    def test_bad_json_rejected(self):
        for text in ['{}', '[3]', '[{"age":NaN}]', '[{"a":1,"a":2}]']:
            with self.subTest(text=text), self.assertRaises((InputError, ValueError)):
                list(records(self.write(text)))

    def test_bad_csv_headers_or_shape(self):
        for text in ['a,a\n1,2', 'a,b\n1,2,3', 'a,b\n1', ',b\n1,2']:
            with self.subTest(text=text), self.assertRaises(InputError):
                list(records(self.write(text, ".csv")))

    def test_partial_run_removed_on_late_failure(self):
        path = self.write(json.dumps(good()) + '\n{broken\n', '.jsonl')
        with self.assertRaises(ValueError):
            run(path, self.root / 'runs')
        self.assertEqual(list((self.root / 'runs').iterdir()), [])

    def test_runs_never_overwrite(self):
        path = self.write(json.dumps([good()]))
        first, _ = run(path, self.root / 'runs')
        second, _ = run(path, self.root / 'runs')
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())

    def test_jsonl_blank_lines(self):
        self.assertEqual(len(list(records(self.write('\n' + json.dumps(good()), '.jsonl')))), 1)

    def test_csv_bom(self):
        path = self.write('\ufeffrecord_id,email,age,country,status\nx,a@b.com,30,US,active\n', '.csv')
        output, summary = run(path, self.root / 'runs')
        self.assertEqual(summary['counts']['REPAIR'], 1)

    def test_empty_array(self):
        _, summary = run(self.write('[]'), self.root / 'runs')
        self.assertEqual(summary['total'], 0)
