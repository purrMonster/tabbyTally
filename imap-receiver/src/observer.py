"""Independent mailbox threads with persistent read-only IMAP connections."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import random
import signal
import threading
import time

import psycopg
from psycopg.rows import dict_row
from .database import connect
from .health import WorkerHealth, publish_health

from .capture import capture_once
from .cli import SetupError, open_mailbox, quote_mailbox, response_number


def log(event, mailbox=None, **fields):
    print(json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                          event=event, mailbox_id=str(mailbox) if mailbox else None,
                          **fields)), flush=True)


def targets(db):
    return db.execute("""SELECT a.imap_host, a.imap_port, a.username,
        a.credential_ref, m.id, m.folder_path, m.initialized_at
        FROM imap_receiver.accounts a JOIN imap_receiver.mailboxes m ON m.account_id=a.id
        WHERE a.enabled AND m.enabled ORDER BY m.id""").fetchall()


def retry_delay(failures):
    return min(300, 2 ** min(failures, 8)) + random.uniform(0, 1)


def error_code(error):
    if isinstance(error, SetupError):
        if 'UIDVALIDITY' in str(error) or 'backwards' in str(error):
            return 'mailbox_identity_changed'
        if 'Initialize' in str(error):
            return 'checkpoint_required'
        if 'owned' in str(error):
            return 'mailbox_owned'
    return type(error).__name__


@contextmanager
def selected(client, target):
    status, data = client.select(quote_mailbox(target['folder_path']), readonly=True)
    if status != 'OK':
        raise SetupError('Read-only reselection failed.')
    yield client, int(data[0])


def session(db, target, stop, interval, report=None):
    lock = db.execute('SELECT pg_try_advisory_lock(hashtextextended(%s::text,0)) AS acquired',
                      (str(target['id']),)).fetchone()
    if not lock['acquired']:
        raise SetupError('Mailbox is owned by another worker.')
    with open_mailbox(target) as (client, _):
        status, capabilities = client.capability()
        idle_supported = status == 'OK' and b'IDLE' in b' '.join(capabilities).upper().split()
        log('mailbox_connected', target['id'], idle=idle_supported)
        due = 0
        while not stop.is_set():
            # This round trip detects loss of the pinned lock connection before capture.
            db.execute('SELECT 1')
            if time.monotonic() >= due:
                result = capture_once(db, target,
                    open_mailbox=lambda _: selected(client, target),
                    response_number=response_number, error=SetupError)
                log('scan_committed', target['id'], **result)
                if report:
                    report(target['id'], 'scanned')
                due = time.monotonic() + interval
                if result['more_pending']:
                    due = 0
                    continue
            duration = max(1, min(10, due - time.monotonic()))
            if idle_supported:
                with client.idle(duration=duration) as idler:
                    for kind, _ in idler:
                        if kind == 'BYE':
                            raise SetupError('Server closed IMAP connection.')
                        if kind in ('EXISTS', 'EXPUNGE'):
                            due = 0
                            break
                        if stop.is_set():
                            break
            else:
                stop.wait(duration)


def worker(target, stop, interval, report=None):
    failures = 0
    while not stop.is_set():
        try:
            with connect() as db:
                try:
                    session(db, target, stop, interval, report)
                except Exception as error:
                    # Never overwrite another owner's diagnostic state.
                    if error_code(error) != 'mailbox_owned':
                        try:
                            db.execute('UPDATE imap_receiver.mailboxes SET last_error_code=%s WHERE id=%s',
                                       (error_code(error), target['id']))
                        except psycopg.Error:
                            pass
                    raise
            return
        except Exception as error:
            failures += 1
            code = error_code(error)
            if report:
                report(target['id'], 'retry', code)
            log('mailbox_retry', target['id'], code=code)
            # Identity/checkpoint faults remain blocked; no automatic baseline reset.
            stop.wait(60 if code in ('mailbox_identity_changed', 'checkpoint_required')
                      else retry_delay(failures))
    log('mailbox_stopped', target['id'])


def reconcile(running, desired, interval, max_workers, report=None):
    desired = {str(target['id']): target for target in desired}
    for key, (thread, stop, target) in list(running.items()):
        if key not in desired or desired[key] != target:
            stop.set()
        if not thread.is_alive():
            del running[key]
    for key, target in desired.items():
        if key in running:
            continue
        if len(running) >= max_workers:
            log('worker_capacity_reached', max_workers=max_workers)
            break
        stop = threading.Event()
        if report:
            report(target['id'], 'starting', 'awaiting_first_scan')
        thread = threading.Thread(target=worker, args=(target, stop, interval, report), daemon=True)
        running[key] = thread, stop, target
        thread.start()


def observe():
    max_workers = int(os.environ.get('MAX_MAILBOX_WORKERS', '8'))
    interval = int(os.environ.get('RECONCILE_SECONDS', '60'))
    if not 1 <= max_workers <= 32 or not 10 <= interval <= 1740:
        raise SetupError('Invalid worker limit or reconciliation interval.')
    shutdown = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: shutdown.set())
    running = {}
    health = WorkerHealth()
    publish_health(running, health, interval, supervisor_error='starting')
    log('observer_started', max_workers=max_workers, reconcile_seconds=interval)
    try:
        while not shutdown.is_set():
            supervisor_error = None
            try:
                with connect() as db:
                    desired = targets(db)
                reconcile(running, desired, interval, max_workers, health.report)
            except Exception as error:
                supervisor_error = type(error).__name__
                log('supervisor_retry', code=type(error).__name__)
            publish_health(running, health, interval, supervisor_error=supervisor_error)
            shutdown.wait(5)
    finally:
        for _, stop, _ in running.values():
            stop.set()
        publish_health(running, health, interval, stopped=True)
        deadline = time.monotonic() + 25
        for thread, _, _ in running.values():
            thread.join(max(0, deadline - time.monotonic()))
        log('observer_stopped', workers_remaining=sum(t.is_alive() for t, _, _ in running.values()))
    return 0
