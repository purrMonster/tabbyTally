"""Run explicitly through the admin service; fixture data always rolls back."""

from contextlib import contextmanager
import os
import unittest

import psycopg
from psycopg.rows import dict_row
from src.capture import capture_once
from src.cli import SetupError
from test_capture import FakeIMAP


@unittest.skipUnless(os.environ.get('RUN_ROLE_TESTS') == '1', 'admin role test opt-in required')
class RuntimePermissionsTests(unittest.TestCase):
    def test_actual_capture_and_denied_operations(self):
        with psycopg.connect(autocommit=True, row_factory=dict_row) as db:
            with db.transaction():
                account = db.execute("""INSERT INTO imap_receiver.accounts
                    (name, imap_host, username, credential_ref) VALUES
                    ('permission fixture','example.invalid','fixture','TEST') RETURNING id""").fetchone()
                target = db.execute("""INSERT INTO imap_receiver.mailboxes
                    (account_id,uid_validity,last_uid,initialized_at)
                    VALUES (%s,7,0,now()) RETURNING id""", (account['id'],)).fetchone()
                db.execute('SET LOCAL ROLE imap_receiver_runtime')
                role = db.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
                self.assertFalse(any(role.values()))
                @contextmanager
                def opener(_):
                    yield FakeIMAP(), 1
                result = capture_once(db, target, open_mailbox=opener,
                    response_number=lambda c,n: 7 if n=='UIDVALIDITY' else 2,
                    error=SetupError)
                self.assertEqual(result['inserted'], 1)
                email = db.execute('SELECT id FROM imap_receiver.emails WHERE mailbox_id=%s', (target['id'],)).fetchone()
                db.execute("""INSERT INTO imap_receiver.attachments
                    (email_id,part_index,size_bytes) VALUES (%s,0,0)""", (email['id'],))
                self.assertEqual(capture_once(db, target, open_mailbox=opener,
                    response_number=lambda c,n: 7 if n=='UIDVALIDITY' else 2,
                    error=SetupError)['inserted'], 0)
                denied = [
                    'DELETE FROM imap_receiver.emails WHERE false',
                    'DELETE FROM imap_receiver.attachments WHERE false',
                    'DELETE FROM imap_receiver.mailboxes WHERE false',
                    'TRUNCATE imap_receiver.attachments',
                    "UPDATE imap_receiver.emails SET subject='forbidden' WHERE false",
                    'UPDATE imap_receiver.accounts SET enabled=false WHERE false',
                    'UPDATE imap_receiver.mailboxes SET enabled=false WHERE false',
                    "UPDATE imap_receiver.mailboxes SET folder_path='forbidden' WHERE false",
                    "INSERT INTO imap_receiver.accounts (name,imap_host,username,credential_ref) VALUES ('x','x','x','x')",
                    'CREATE TABLE imap_receiver.forbidden_test (id int)',
                    'CREATE SCHEMA forbidden_permission_test',
                    'CREATE ROLE forbidden_permission_test',
                ]
                for statement in denied:
                    with self.subTest(statement=statement):
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            with db.transaction():
                                db.execute(statement)
                                # If unexpectedly allowed, roll back the test statement anyway.
                                raise psycopg.Rollback()
                raise psycopg.Rollback()
