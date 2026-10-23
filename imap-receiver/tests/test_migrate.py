"""Disposable databases only; never migrate or drop the configured live database."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from psycopg import sql
from src.database import connect
from src.backup import fingerprint
from src import migrate


class MigrationFileTests(unittest.TestCase):
    def test_line_endings_do_not_change_checksum(self):
        original = migrate.load_migrations()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in migrate.DIRECTORY.iterdir():
                if file.suffix in ('.json', '.sql'):
                    (root / file.name).write_bytes(file.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            with patch.object(migrate, 'DIRECTORY', root):
                self.assertEqual(original, migrate.load_migrations())


@unittest.skipUnless(os.environ.get('RUN_MIGRATION_TESTS') == '1', 'disposable database test opt-in required')
class MigrationDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.admin = connect()
        self.target = 'imap_migrationtest_' + uuid.uuid4().hex
        self.created = False
        self.db = None
        self.addCleanup(self.cleanup_database)
        self.admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(self.target)))
        self.created = True
        self.admin.execute(sql.SQL('REVOKE CONNECT ON DATABASE {} FROM PUBLIC').format(sql.Identifier(self.target)))
        self.db = connect(dbname=self.target)

    def cleanup_database(self):
        if self.db:
            self.db.close()
        try:
            if self.created:
                self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.target)))
        finally:
            self.admin.close()

    def legacy(self):
        self.db.execute(migrate.load_migrations()[0]['source'])

    def test_fresh_install_repeat_and_backup_fingerprint(self):
        self.assertEqual(migrate.migrate(self.db, status_only=True)['state'], 'empty')
        self.assertEqual(migrate.migrate(self.db)['applied_now'], 1)
        self.assertEqual(migrate.migrate(self.db)['applied_now'], 0)
        with self.db.transaction():
            result = fingerprint(self.db)
        self.assertEqual(result['tables']['schema_migrations']['rows'], 1)
        self.assertEqual(result['tables']['emails']['rows'], 0)

    def test_adoption_requires_flag_and_preserves_rows(self):
        self.legacy()
        self.db.execute("""INSERT INTO imap_receiver.accounts
            (name,imap_host,username,credential_ref) VALUES
            ('fixture','example.invalid','test@example.com','TEST')""")
        with self.db.transaction():
            before = fingerprint(self.db)
        with self.assertRaises(ValueError):
            migrate.migrate(self.db)
        result = migrate.migrate(self.db, adopt_existing=True)
        self.assertTrue(result['adopted'])
        with self.db.transaction():
            after = fingerprint(self.db, include_migrations=False)
        self.assertEqual(before, after)

    def test_schema_drift_rejected_without_adoption(self):
        self.legacy()
        self.db.execute('ALTER TABLE imap_receiver.accounts ADD COLUMN unexpected text')
        with self.assertRaises(ValueError):
            migrate.migrate(self.db, adopt_existing=True)
        self.assertIsNone(self.db.execute("SELECT to_regclass('imap_receiver.schema_migrations') AS ledger").fetchone()['ledger'])

    def test_modified_history_rejected(self):
        migrate.migrate(self.db)
        self.db.execute("UPDATE imap_receiver.schema_migrations SET sha256=repeat('a',64)")
        with self.assertRaises(ValueError):
            migrate.migrate(self.db)

    def test_failed_migration_rolls_back_entire_schema(self):
        with patch.object(migrate, 'fingerprint', side_effect=ValueError('mismatch')):
            with self.assertRaises(ValueError):
                migrate.migrate(self.db)
        self.assertIsNone(self.db.execute("SELECT to_regnamespace('imap_receiver') AS schema").fetchone()['schema'])

    def test_concurrent_runner_rejected(self):
        with connect(dbname=self.target) as other, other.transaction():
            other.execute('SELECT pg_advisory_xact_lock(%s)', (migrate.LOCK,))
            with self.assertRaises(ValueError):
                migrate.migrate(self.db)
        self.assertEqual(migrate.migrate(self.db)['applied_now'], 1)


if __name__ == '__main__':
    unittest.main()
