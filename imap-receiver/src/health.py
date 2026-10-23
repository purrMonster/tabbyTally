"""Read-only process/progress health probe; no mailbox connections or state writes."""

import json
import os
from pathlib import Path
import threading
import time

from .database import connect

HEALTH_FILE = Path('/tmp/imap-receiver-health.json')


class WorkerHealth:
    def __init__(self):
        self.lock = threading.Lock()
        self.states = {}

    def report(self, mailbox_id, state, code=None):
        with self.lock:
            previous = self.states.get(str(mailbox_id), {})
            self.states[str(mailbox_id)] = dict(
                state=state, code=code,
                last_success=time.monotonic() if state == 'scanned' else previous.get('last_success'))

    def snapshot(self, running):
        with self.lock:
            return {key: dict(self.states.get(key, {}), alive=thread.is_alive(),
                              stopping=stop.is_set())
                    for key, (thread, stop, _) in running.items()}


def publish_health(running, health, interval, supervisor_error=None, stopped=False):
    snapshot = dict(pid=os.getpid(), heartbeat=time.monotonic(), interval=interval,
                    supervisor_error=supervisor_error, stopped=stopped,
                    workers=health.snapshot(running))
    temporary = HEALTH_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot), encoding='utf-8')
    temporary.replace(HEALTH_FILE)


def evaluate(snapshot, rows, now, scan_max_age):
    reasons = []
    if snapshot.get('stopped'):
        reasons.append(dict(code='observer_stopped'))
    age = now - snapshot['heartbeat']
    if age < 0 or age > 30:
        reasons.append(dict(code='supervisor_stale'))
    if snapshot.get('supervisor_error'):
        reasons.append(dict(code='supervisor_error'))
    workers = snapshot.get('workers', {})
    for row in rows:
        key = str(row['id'])
        def fail(code):
            reasons.append(dict(mailbox_id=key, code=code))
        state = workers.get(key)
        if not state or not state.get('alive'):
            fail('worker_missing')
        elif state.get('stopping'):
            fail('worker_stopping')
        else:
            if state.get('code'):
                fail('worker_retry')
            success = state.get('last_success')
            if success is None:
                fail('worker_not_scanned')
            elif now - success < 0 or now - success > scan_max_age:
                fail('worker_scan_stale')
        if row['initialized_at'] is None:
            fail('checkpoint_required')
        if row['last_error_code']:
            fail('mailbox_error')
        if row['scan_age'] is None or row['scan_age'] > scan_max_age or row['scan_age'] < -30:
            fail('database_scan_stale')
    return dict(healthy=not reasons, mode='observing' if rows else 'idle',
                enabled_mailboxes=len(rows), reasons=reasons)


def probe():
    try:
        snapshot = json.loads(HEALTH_FILE.read_text(encoding='utf-8'))
        os.kill(snapshot['pid'], 0)
        interval = int(snapshot['interval'])
        threshold = int(os.environ.get('HEALTH_SCAN_MAX_AGE_SECONDS', max(180, 3 * interval)))
        if threshold < interval or threshold > 86400:
            raise ValueError('Invalid scan threshold')
        with connect(connect_timeout=3, options='-c statement_timeout=3000') as db:
            rows = db.execute("""SELECT m.id, m.initialized_at, m.last_error_code,
                EXTRACT(EPOCH FROM (clock_timestamp() - m.last_scan_at)) AS scan_age
                FROM imap_receiver.mailboxes m JOIN imap_receiver.accounts a ON a.id=m.account_id
                WHERE a.enabled AND m.enabled""").fetchall()
        result = evaluate(snapshot, rows, time.monotonic(), threshold)
    except FileNotFoundError:
        result = dict(healthy=False, reasons=[dict(code='heartbeat_missing')])
    except ProcessLookupError:
        result = dict(healthy=False, reasons=[dict(code='observer_missing')])
    except Exception as error:
        result = dict(healthy=False, reasons=[dict(code='probe_failed', error_type=type(error).__name__)])
    print(json.dumps(result), flush=True)
    return 0 if result['healthy'] else 1


if __name__ == '__main__':
    raise SystemExit(probe())
