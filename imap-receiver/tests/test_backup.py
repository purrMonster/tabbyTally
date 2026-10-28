import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src import backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(backup, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.name = 'receiver_20261015T000000Z_' + 'a' * 32 + '.dump'
        self.archive = self.root / self.name
        self.archive.write_bytes(b'test archive')
        self.expected = {'tables': {}, 'schema_sha256': 'test', 'raw_hash_mismatches': 0}
        self.manifest = {'format_version': 1, 'archive': self.name,
                         'scope': 'imap_receiver schema',
                         'archive_sha256': hashlib.sha256(b'test archive').hexdigest(),
                         'fingerprint': self.expected}
        self.archive.with_suffix('.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_reject_paths_and_arbitrary_filenames(self):
        for name in ('../' + self.name, '/backups/' + self.name, 'live.dump', self.name + '.partial'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                backup.archive_path(name)

    @patch('src.backup.connect')
    def test_tampered_archive_never_connects(self, connect):
        self.archive.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            backup.verify_backup(self.name)
        connect.assert_not_called()

    @patch('src.backup.connect')
    def test_missing_manifest_never_connects(self, connect):
        self.archive.with_suffix('.json').unlink()
        with self.assertRaises(FileNotFoundError):
            backup.verify_backup(self.name)
        connect.assert_not_called()

    def setup_database(self, connect):
        admin = MagicMock()
        restored = MagicMock()
        connect.side_effect = [admin, restored]
        admin.__enter__.return_value = admin
        restored.__enter__.return_value = restored
        admin.execute.return_value.fetchone.return_value = {'name': 'imap_receiver'}
        return admin

    @patch('src.backup.fingerprint')
    @patch('src.backup.run_pg')
    @patch('src.backup.connect')
    def test_restore_verified_and_cleaned(self, connect, run_pg, fingerprint):
        admin = self.setup_database(connect)
        fingerprint.return_value = self.expected
        backup.verify_backup(self.name)
        args = run_pg.call_args.args[0]
        self.assertIn('--single-transaction', args)
        self.assertIn('--no-owner', args)
        self.assertTrue(any(arg.startswith('--dbname=imap_restorecheck_') for arg in args))
        self.assertNotIn('--create', args)
        self.assertIn('DROP DATABASE', str(admin.execute.call_args.args[0]))
        self.assertEqual(len(list(self.root.glob('*.verified.*.json'))), 1)

    @patch('src.backup.run_pg', side_effect=RuntimeError('private tool output'))
    @patch('src.backup.connect')
    def test_failed_restore_still_cleans_own_database(self, connect, run_pg):
        admin = self.setup_database(connect)
        with self.assertRaises(RuntimeError):
            backup.verify_backup(self.name)
        self.assertIn('DROP DATABASE', str(admin.execute.call_args.args[0]))
        self.assertEqual(list(self.root.glob('*.verified.*.json')), [])

    @patch('src.backup.fingerprint', return_value={'changed': True})
    @patch('src.backup.run_pg')
    @patch('src.backup.connect')
    def test_mismatch_fails_and_cleans(self, connect, run_pg, fingerprint):
        admin = self.setup_database(connect)
        with self.assertRaises(ValueError):
            backup.verify_backup(self.name)
        self.assertIn('DROP DATABASE', str(admin.execute.call_args.args[0]))
        self.assertEqual(list(self.root.glob('*.verified.*.json')), [])

    @patch('src.backup.run_pg')
    @patch('src.backup.connect')
    def test_creation_collision_never_drops_existing_database(self, connect, run_pg):
        admin = self.setup_database(connect)
        admin.execute.side_effect = [MagicMock(fetchone=lambda: {'name': 'imap_receiver'}), RuntimeError('exists')]
        with self.assertRaises(RuntimeError):
            backup.verify_backup(self.name)
        self.assertEqual(admin.execute.call_count, 2)
        run_pg.assert_not_called()

    @patch('src.backup.subprocess.run')
    def test_pg_failure_does_not_expose_stderr(self, run):
        run.return_value = MagicMock(returncode=1, stderr=b'private SQL and credentials')
        with self.assertRaises(RuntimeError) as error:
            backup.run_pg(['pg_dump'])
        self.assertNotIn('private', str(error.exception))


if __name__ == '__main__':
    unittest.main()
