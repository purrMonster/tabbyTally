from psycopg.types.json import Jsonb


def audit(db, action, target, reason):
    if not reason or len(reason)>500:
        raise ValueError('A bounded audit reason is required')
    db.execute('INSERT INTO processing.operator_actions(action,target,reason) VALUES (%s,%s,%s)',
               (action, str(target), reason))


def activate(db, version, mailbox_ids=(), email_ids=(), config=None, reason='explicit activation', mode='fake'):
    config = config or {'scenario': 'success'}
    allowed = {'scenario', 'failures', 'delay'}
    if mode not in ('fake','extract'):
        raise ValueError('Invalid processing mode')
    if mode=='extract':
        required = {'model_identity','profile','schema_version','rule_version','normalizer_version','template_version'}
        if set(config)!=required or any(not isinstance(v,str) or not v or len(v)>128 for v in config.values()):
            raise ValueError('Invalid extraction configuration')
    elif set(config)-allowed or config.get('scenario') not in ('success','review','transient','permanent','delay'):
        raise ValueError('Invalid fake configuration')
    if not 0 <= config.get('failures', 0) <= 100 or not 0 <= config.get('delay', 0) <= 120:
        raise ValueError('Invalid fake limits')
    if bool(mailbox_ids) == bool(email_ids):
        raise ValueError('Select mailboxes or explicit emails')
    with db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        db.execute("INSERT INTO processing.pipeline_versions(id,mode,config) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                   (version, mode, Jsonb(config)))
        saved = db.execute('SELECT mode,config FROM processing.pipeline_versions WHERE id=%s', (version,)).fetchone()
        if saved['config'] != config or saved['mode'] != mode:
            raise ValueError('Version configuration is immutable')
        run = db.execute('INSERT INTO processing.processing_runs(pipeline_version,kind) VALUES (%s,%s) RETURNING id',
                         (version, 'live' if mailbox_ids else 'sample')).fetchone()['id']
        for mailbox in set(mailbox_ids):
            row = db.execute('SELECT uid_validity,last_uid,initialized_at FROM imap_receiver.mailboxes WHERE id=%s', (mailbox,)).fetchone()
            if not row or row['initialized_at'] is None:
                raise ValueError('Mailbox not initialized')
            db.execute('INSERT INTO processing.run_mailbox_boundaries(run_id,mailbox_id,uid_validity,last_uid) VALUES (%s,%s,%s,%s)',
                       (run, mailbox, row['uid_validity'], row['last_uid']))
        for email in set(email_ids):
            db.execute('INSERT INTO processing.run_email_selections(run_id,email_id) VALUES (%s,%s)', (run, email))
        audit(db, 'activate', run, reason)
        return run


def reconcile(db, limit=100):
    if not 1 <= limit <= 1000:
        raise ValueError('Invalid batch size')
    with db.transaction():
        # Each sweep restarts at the fixed scope; no late-commit cursor gaps.
        changed = db.execute("""SELECT DISTINCT b.run_id FROM processing.run_mailbox_boundaries b
            JOIN imap_receiver.mailboxes m ON m.id=b.mailbox_id
            JOIN processing.processing_runs r ON r.id=b.run_id
            WHERE r.enabled AND m.uid_validity IS DISTINCT FROM b.uid_validity""").fetchall()
        # Discovery cannot change activation configuration; mismatched runs are excluded
        # and returned as an operational signal for explicit operator reconciliation.
        rows = db.execute("""WITH eligible AS (
            SELECT e.id AS email_id,r.id AS run_id,r.pipeline_version
            FROM processing.processing_runs r JOIN processing.run_mailbox_boundaries b ON b.run_id=r.id
            JOIN imap_receiver.mailboxes m ON m.id=b.mailbox_id AND m.uid_validity=b.uid_validity
            JOIN imap_receiver.emails e ON e.mailbox_id=b.mailbox_id AND e.uid_validity=b.uid_validity AND e.uid>b.last_uid
            WHERE r.enabled
            UNION ALL
            SELECT s.email_id,r.id,r.pipeline_version FROM processing.processing_runs r
            JOIN processing.run_email_selections s ON s.run_id=r.id WHERE r.enabled
        ), missing AS (
            SELECT DISTINCT ON (e.email_id,e.pipeline_version) e.* FROM eligible e
            WHERE NOT EXISTS (SELECT 1 FROM processing.email_jobs j
                WHERE j.email_id=e.email_id AND j.pipeline_version=e.pipeline_version)
            ORDER BY e.email_id,e.pipeline_version,e.run_id LIMIT %s
        ) INSERT INTO processing.email_jobs(email_id,run_id,pipeline_version)
        SELECT email_id,run_id,pipeline_version FROM missing ON CONFLICT DO NOTHING RETURNING id""", (limit,)).fetchall()
        return {'inserted': len(rows), 'uidvalidity_mismatches': len(changed)}


def set_enabled(db, run_id, enabled, reason):
    with db.transaction():
        if not db.execute('UPDATE processing.processing_runs SET enabled=%s WHERE id=%s RETURNING id', (enabled, run_id)).fetchone():
            raise ValueError('Unknown run')
        audit(db, 'resume' if enabled else 'pause', run_id, reason)


def retry(db, job_id, allowance, reason):
    if not 1 <= allowance <= 10:
        raise ValueError('Allowance must be 1..10')
    with db.transaction():
        row = db.execute("""UPDATE processing.email_jobs SET state='queued',attempt_limit=attempts+%s,
            due_at=clock_timestamp() WHERE id=%s AND state='dead' RETURNING id""", (allowance, job_id)).fetchone()
        if not row:
            raise ValueError('Only dead jobs can be retried')
        audit(db, 'retry', job_id, reason)


def invalidate_leases(db, reason):
    """Admin-only restore operation, after old workers have been stopped/fenced."""
    with db.transaction():
        rows = db.execute("""UPDATE processing.email_jobs
            SET lease_expires_at=clock_timestamp()-interval '1 second'
            WHERE state='leased' RETURNING id""").fetchall()
        audit(db, 'invalidate_restored_leases', 'all', reason)
        db.execute("UPDATE processing.notification_outbox SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE state='leased'")
        return len(rows)
