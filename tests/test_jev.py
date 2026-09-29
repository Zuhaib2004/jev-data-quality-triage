import copy
import json
import unittest

import httpx

from jev_triage.jev import ENDPOINT, JevClient, JevError, REASONS
from jev_triage.models import Decision
from jev_triage.rules import inspect


def response():
    return {"model": "jev-test", "answers": {
        "decision": {"type": "choice", "choice": "ACCEPT", "confidence": 0.98,
                     "probabilities": {"ACCEPT": 0.99, "REPAIR": 0.005, "QUARANTINE": 0.005}},
        "reason": {"type": "choice", "choice": "CONSISTENT", "confidence": 0.99,
                   "probabilities": {key: float(key == 'CONSISTENT') for key in REASONS}},
    }}


class JevTests(unittest.TestCase):
    def check(self):
        return inspect({"record_id": "private-id", "email": "private@example.com", "age": 104,
                        "country": "US", "status": "active", "notes": "confirmed active"})

    def client(self, handler):
        http = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http.close)
        return JevClient("test-key", client=http, sleep=lambda _: None)

    def test_contract_and_data_minimization(self):
        def handler(request):
            self.assertEqual(str(request.url), ENDPOINT)
            self.assertEqual(request.headers['authorization'], 'Bearer test-key')
            payload = json.loads(request.content)
            self.assertEqual(payload['questions']['decision']['type'], 'choice')
            self.assertEqual(set(payload['questions']['decision']['criteria']), set(Decision))
            self.assertNotIn('private-id', request.content.decode())
            self.assertNotIn('private@example.com', request.content.decode())
            return httpx.Response(200, json=response())
        self.assertEqual(self.client(handler).decide(self.check()).decision, Decision.ACCEPT)

    def test_bad_responses_fail_closed(self):
        variants = []
        for change in [dict(choice='DELETE'), dict(type='text'), dict(confidence=float('nan')),
                       dict(confidence=2), dict(confidence=True), dict(probabilities={}),
                       dict(probabilities={'ACCEPT': .2, 'REPAIR': .7, 'QUARANTINE': .1}),
                       dict(probabilities={'ACCEPT': .9, 'REPAIR': .9, 'QUARANTINE': .1})]:
            body = copy.deepcopy(response())
            body['answers']['decision'].update(change)
            variants.append(body)
        variants += [{}, {'answers': []}]
        for body in variants:
            with self.subTest(body=body), self.assertRaises(JevError):
                self.client(lambda _: httpx.Response(200, content=json.dumps(body))).decide(self.check())

    def test_retry_rate_limit(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429 if len(calls) < 3 else 200, json=response())
        self.client(handler).decide(self.check())
        self.assertEqual(len(calls), 3)

    def test_auth_failure_not_retried(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(401, text='secret response')
        with self.assertRaises(JevError) as caught:
            self.client(handler).decide(self.check())
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(len(calls), 1)

    def test_timeout_retries_bounded(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout('timeout')
        with self.assertRaises(JevError):
            self.client(handler).decide(self.check())
        self.assertEqual(len(calls), 3)

    def test_missing_key(self):
        with self.assertRaises(ValueError):
            JevClient(None)
