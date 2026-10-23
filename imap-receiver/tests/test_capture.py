from contextlib import contextmanager
import os
import unittest

import psycopg
from psycopg.rows import dict_row
from src.capture import capture_once, clean, parse_source
from src.cli import SetupError

RAW = (b'From: Sender <sender@example.com>\r\nTo: receiver@example.com\r\n'
       b'Subject: Capture fixture\r\nDate: Thu, 15 Oct 2026 10:00:00 +0530\r\n'
       b'Content-Type: text/plain; charset=utf-8\r\n\r\nHello fixture.\r\n')


class ParserTests(unittest.TestCase):
    def test_plain_email_and_missing_message_id(self):
        parsed = parse_source(RAW)
        self.assertEqual(parsed['subject'], 'Capture fixture')
        self.assertIn('Hello fixture.', parsed['text_body'])
        self.assertEqual(parsed['from_addresses'][0]['address'], 'sender@example.com')
        self.assertIsNone(parsed['message_id'])
        self.assertIsNotNone(parsed['message_date'].tzinfo)

    def test_malformed_multipart_retains_failure(self):
        self.assertEqual(parse_source(b'Content-Type: multipart/mixed\r\n\r\nbad')['capture_status'], 'parse_failed')

    def test_attachment_and_html(self):
        from email.message import EmailMessage
        message = EmailMessage()
        message.set_content('plain')
        message.add_alternative('<p>html</p>', subtype='html')
        message.add_attachment(b'abc', maintype='application', subtype='octet-stream', filename='test.bin')
        parsed = parse_source(message.as_bytes())
        self.assertIn('html', parsed['html_body'])
        self.assertEqual(parsed['attachments'][0]['size_bytes'], 3)

    def test_nul_sanitization(self):
        self.assertEqual(clean({'subject': 'a\x00b'}), {'subject': 'a\ufffdb'})


class FakeIMAP:
    def __init__(self):
        self.metadata_calls = 0
        self.fail_after_source = False

    def uid(self, command, *args):
        if command == 'SEARCH':
            return 'OK', [b'1']
        if 'BODY.PEEK' in args[-1]:
            return 'OK', [(b'1 (UID 1 BODY[]', RAW), b')']
        self.metadata_calls += 1
        if self.fail_after_source and self.metadata_calls == 2:
            return 'NO', []
        return 'OK', [f'1 (UID 1 RFC822.SIZE {len(RAW)} INTERNALDATE "15-Oct-2026 10:00:00 +0530" FLAGS ())'.encode()]


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'explicit database test opt-in required')
class TransactionTests(unittest.TestCase):
    def test_replay_rollback_and_generation_guard(self):
        with psycopg.connect(autocommit=True, row_factory=dict_row) as db:
            with db.transaction():
                account = db.execute("""INSERT INTO imap_receiver.accounts
                    (name, imap_host, username, credential_ref) VALUES
                    ('test fixture', 'invalid.example', 'fixture', 'TEST') RETURNING id""").fetchone()
                target = db.execute("""INSERT INTO imap_receiver.mailboxes
                    (account_id, uid_validity, last_uid, initialized_at)
                    VALUES (%s, 7, 0, now()) RETURNING id""", (account['id'],)).fetchone()
                fake = FakeIMAP()
                @contextmanager
                def opener(_):
                    yield fake, 1
                def run(validity=7, **kwargs):
                    return capture_once(db, target, open_mailbox=opener,
                        response_number=lambda c, n: validity if n == 'UIDVALIDITY' else 2,
                        error=SetupError, **kwargs)
                self.assertEqual(run()['inserted'], 1)
                self.assertEqual(run()['examined'], 0)
                db.execute('UPDATE imap_receiver.mailboxes SET last_uid=0 WHERE id=%s', (target['id'],))
                self.assertEqual(run()['inserted'], 0)
                db.execute('DELETE FROM imap_receiver.emails WHERE mailbox_id=%s', (target['id'],))
                db.execute('UPDATE imap_receiver.mailboxes SET last_uid=0 WHERE id=%s', (target['id'],))
                fake.metadata_calls = 0
                fake.fail_after_source = True
                with self.assertRaises(SetupError):
                    run()
                self.assertEqual(db.execute('SELECT count(*) AS n FROM imap_receiver.emails WHERE mailbox_id=%s', (target['id'],)).fetchone()['n'], 0)
                self.assertEqual(db.execute('SELECT last_uid FROM imap_receiver.mailboxes WHERE id=%s', (target['id'],)).fetchone()['last_uid'], 0)
                with self.assertRaises(SetupError):
                    run(validity=8)
                fake.fail_after_source = False
                self.assertEqual(run(max_bytes=1)['oversized'], 1)
                raise psycopg.Rollback()
