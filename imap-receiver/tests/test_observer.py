import threading
import unittest
from unittest.mock import MagicMock, patch

from src.cli import SetupError
from src.observer import error_code, reconcile, retry_delay, session


class ObserverTests(unittest.TestCase):
    def test_blocked_errors_classified(self):
        self.assertEqual(error_code(SetupError('UIDVALIDITY changed')), 'mailbox_identity_changed')
        self.assertEqual(error_code(SetupError('Initialize mailbox')), 'checkpoint_required')

    def test_backoff_bounded(self):
        self.assertLess(retry_delay(100), 301)

    @patch('src.observer.threading.Thread')
    def test_worker_limit_and_independent_workers(self, factory):
        running = {}
        reconcile(running, [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}], 60, 2)
        self.assertEqual(set(running), {'a', 'b'})
        self.assertEqual(factory.call_count, 2)
        self.assertIsNot(running['a'][1], running['b'][1])
        reconcile(running, [{'id': 'b'}], 60, 2)
        self.assertTrue(running['a'][1].is_set())
        self.assertFalse(running['b'][1].is_set())

    @patch('src.observer.open_mailbox')
    def test_lock_conflict_prevents_imap(self, opener):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {'acquired': False}
        with self.assertRaises(SetupError):
            session(db, {'id': 'a'}, threading.Event(), 60)
        opener.assert_not_called()

    @patch('src.observer.capture_once')
    @patch('src.observer.open_mailbox')
    def test_idle_notification_triggers_second_scan(self, opener, capture):
        stop = threading.Event()
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {'acquired': True}
        client = MagicMock()
        opener.return_value.__enter__.return_value = (client, 1)
        client.capability.return_value = ('OK', [b'IMAP4rev1 IDLE'])
        client.idle.return_value.__enter__.return_value = iter([('EXISTS', [b'2'])])
        def scanned(*args, **kwargs):
            if capture.call_count == 2:
                stop.set()
            return {'more_pending': False}
        capture.side_effect = scanned
        session(db, {'id': 'a'}, stop, 60)
        self.assertEqual(capture.call_count, 2)
