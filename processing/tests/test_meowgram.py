import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit
from tabby_processing import meowgram

KEY = '00000000-0000-0000-0000-000000000001'
PAYLOAD = {'review_id': KEY, 'revision': 1, 'state': 'open', 'message': 'PRIVATE EMAIL'}


class MeowGramTests(unittest.TestCase):
    def test_payload_whitelist_and_validation(self):
        body = meowgram.message(PAYLOAD)
        self.assertEqual(set(body), {'text_content'})
        self.assertNotIn('PRIVATE EMAIL', body['text_content'])
        for changed in ({'revision': True}, {'revision': 0}, {'state': 'unexpected'}, {'review_id': 'bad'}):
            with self.assertRaises(ValueError): meowgram.message(PAYLOAD | changed)

    def test_not_enabled_by_default(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            meowgram.config()

    def test_reject_unsafe_endpoints(self):
        for url in ('http://example.test/send', 'https://user:password@example.test/send',
                    'https://example.test/send?token=secret', 'https://example.test/'):
            with patch.dict('os.environ', {'MEOWGRAM_VERIFIED_CONTRACT': meowgram.CONTRACT,
                                          'MEOWGRAM_SEND_URL': url}), self.assertRaises(ValueError):
                meowgram.config()

    def deliver(self, status, receipt):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = receipt if isinstance(receipt, bytes) else json.dumps(receipt).encode()
        with (patch.object(meowgram, 'config', return_value=(urlsplit('https://example.test/api/send'), 'bot', 'secret')),
              patch.object(meowgram.http.client, 'HTTPSConnection', return_value=connection)):
            meowgram.deliver(PAYLOAD, KEY)
        return connection

    def test_durable_receipt_and_repeat_key(self):
        for status in (200, 201):
            connection = self.deliver(status, {'id': 'stored-message', 'idempotency_key': KEY, 'persisted': True})
            args = connection.request.call_args.args
            self.assertEqual(args[0:2], ('POST', '/api/send'))
            self.assertEqual(args[3]['Idempotency-Key'], KEY)
            self.assertNotIn('PRIVATE EMAIL', args[2].decode())
            connection.close.assert_called_once()

    def test_failure_does_not_acknowledge(self):
        for status, receipt in ((202, {}), (302, {}), (401, {}), (409, {}), (429, {}), (503, {}),
                                (200, {}), (200, b'bad json'), (200, b'x'*16385),
                                (200, {'id': 'x', 'idempotency_key': 'other', 'persisted': True}),
                                (200, {'id': 'x', 'idempotency_key': KEY, 'persisted': False})):
            with self.subTest(status=status, receipt=str(receipt)[:40]), self.assertRaises(ValueError):
                self.deliver(status, receipt)

    def test_whole_request_deadline_and_suppressed_output(self):
        with patch.object(meowgram.subprocess, 'run') as run:
            meowgram.send(PAYLOAD, KEY, timeout=20)
        self.assertEqual(run.call_args.kwargs['timeout'], 20)
        self.assertTrue(run.call_args.kwargs['check'])
        self.assertEqual(run.call_args.kwargs['stderr'], meowgram.subprocess.DEVNULL)
