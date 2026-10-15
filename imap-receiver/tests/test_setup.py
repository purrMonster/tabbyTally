import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.cli import SetupError, initialize, quote_mailbox, read_password, response_number


class SetupTests(unittest.TestCase):
    def test_password_whitespace_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'secret'
            path.write_bytes(b' space\r\n')
            with patch.dict(os.environ, {'TEST_FILE': str(path)}):
                self.assertEqual(read_password('TEST'), ' space\r\n')

    def test_missing_reference(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SetupError):
                read_password('MISSING')

    def test_mailbox_quoting(self):
        self.assertEqual(quote_mailbox('Bank Alerts'), '"Bank Alerts"')
        with self.assertRaises(SetupError):
            quote_mailbox('INBOX\r\nLOGOUT')

    def test_uid_validation(self):
        client = MagicMock()
        client.response.return_value = ('UIDNEXT', [b'251'])
        self.assertEqual(response_number(client, 'UIDNEXT'), 251)
        for invalid in [None, b'0', b'bad', b'4294967296']:
            client.response.return_value = ('UIDNEXT', [invalid])
            with self.assertRaises(SetupError):
                response_number(client, 'UIDNEXT')

    @patch('src.cli.open_mailbox')
    def test_existing_checkpoint_never_contacts_imap(self, connect):
        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [
            {'acquired': True}, {'initialized_at': 'already set'}]
        self.assertFalse(initialize(db, {'id': 'test'}))
        connect.assert_not_called()
        self.assertEqual(db.execute.call_count, 2)

    @patch('src.cli.open_mailbox')
    def test_lock_contention_never_contacts_imap(self, connect):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {'acquired': False}
        with self.assertRaises(SetupError):
            initialize(db, {'id': 'test'})
        connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
