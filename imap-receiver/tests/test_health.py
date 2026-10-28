import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.health import WorkerHealth, evaluate, probe, publish_health


class HealthTests(unittest.TestCase):
    def fixture(self):
        snapshot = dict(pid=123, heartbeat=100, interval=60, stopped=False,
                        supervisor_error=None,
                        workers={'a': dict(alive=True, stopping=False, code=None, last_success=95)})
        rows = [dict(id='a', initialized_at='set', last_error_code=None, scan_age=5)]
        return snapshot, rows

    def test_healthy_and_idle(self):
        snapshot, rows = self.fixture()
        self.assertTrue(evaluate(snapshot, rows, 110, 180)['healthy'])
        result = evaluate(snapshot, [], 110, 180)
        self.assertTrue(result['healthy'])
        self.assertEqual(result['mode'], 'idle')

    def test_stale_supervisor_and_scan(self):
        snapshot, rows = self.fixture()
        result = evaluate(snapshot, rows, 400, 180)
        codes = {r['code'] for r in result['reasons']}
        self.assertIn('supervisor_stale', codes)
        self.assertIn('worker_scan_stale', codes)

    def test_missing_dead_and_stopping_worker(self):
        for state in [None, dict(alive=False), dict(alive=True, stopping=True)]:
            snapshot, rows = self.fixture()
            snapshot['workers'] = {} if state is None else {'a': state}
            self.assertFalse(evaluate(snapshot, rows, 110, 180)['healthy'])

    def test_blocked_mailbox_and_stale_db(self):
        snapshot, rows = self.fixture()
        rows[0].update(initialized_at=None, last_error_code='checkpoint_required', scan_age=None)
        result = evaluate(snapshot, rows, 110, 180)
        self.assertEqual({r['code'] for r in result['reasons']},
                         {'checkpoint_required', 'mailbox_error', 'database_scan_stale'})

    def test_worker_retry_and_first_scan(self):
        snapshot, rows = self.fixture()
        snapshot['workers']['a'].update(code='auth_error', last_success=None)
        codes = {r['code'] for r in evaluate(snapshot, rows, 110, 180)['reasons']}
        self.assertIn('worker_retry', codes)
        self.assertIn('worker_not_scanned', codes)

    def test_stopped_and_supervisor_error(self):
        snapshot, rows = self.fixture()
        snapshot.update(stopped=True, supervisor_error='database_error')
        self.assertFalse(evaluate(snapshot, rows, 110, 180)['healthy'])

    def test_atomic_snapshot_and_success_clears_error(self):
        health = WorkerHealth()
        health.report('a', 'retry', 'error')
        health.report('a', 'scanned')
        thread, stop = MagicMock(), MagicMock()
        thread.is_alive.return_value = True
        stop.is_set.return_value = False
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'health.json'
            with patch('src.health.HEALTH_FILE', path):
                publish_health({'a': (thread, stop, {})}, health, 60)
            data = json.loads(path.read_text())
            self.assertIsNone(data['workers']['a']['code'])
            self.assertIsNotNone(data['workers']['a']['last_success'])
            self.assertFalse(path.with_suffix('.tmp').exists())

    @patch('src.health.connect', side_effect=RuntimeError('private connection text'))
    @patch('src.health.os.kill')
    def test_database_failure_redacts_details(self, kill, connect):
        snapshot, _ = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'health.json'
            path.write_text(json.dumps(snapshot))
            with patch('src.health.HEALTH_FILE', path), patch('builtins.print') as output:
                self.assertEqual(probe(), 1)
            self.assertNotIn('private', str(output.call_args))

    def test_missing_heartbeat(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('src.health.HEALTH_FILE', Path(folder)/'missing'), patch('builtins.print'):
                self.assertEqual(probe(), 1)
