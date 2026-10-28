"""All authoritative transitions serialize on the job row."""
import random
import re
import uuid

from psycopg.types.json import Jsonb


class LostLease(Exception):
    pass


def claim(db, lease_seconds=180):
    if not 1 <= lease_seconds <= 3600:
        raise ValueError('Invalid lease')
    with db.transaction():
        row = db.execute("""SELECT j.* FROM processing.email_jobs j
            JOIN processing.processing_runs r ON r.id=j.run_id
            WHERE r.enabled AND j.state IN ('queued','retry_wait')
            AND j.due_at<=clock_timestamp() AND j.attempts<j.attempt_limit
            ORDER BY j.due_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1""").fetchone()
        if not row:
            return None
        token = uuid.uuid4()
        job = db.execute("""UPDATE processing.email_jobs SET state='leased',attempts=attempts+1,
            lease_token=%s,lease_expires_at=clock_timestamp()+%s*interval '1 second'
            WHERE id=%s RETURNING *""", (token, lease_seconds, row['id'])).fetchone()
        attempt = db.execute("""INSERT INTO processing.job_attempts(job_id,number,token)
            VALUES (%s,%s,%s) RETURNING id""", (job['id'], job['attempts'], token)).fetchone()
        job['attempt_id'] = attempt['id']
        return job


def owned(db, job_id, token):
    row = db.execute('SELECT * FROM processing.email_jobs WHERE id=%s FOR UPDATE', (job_id,)).fetchone()
    now = db.execute('SELECT clock_timestamp() AS now').fetchone()['now']
    if not row or row['state'] != 'leased' or row['lease_token'] != token or row['lease_expires_at'] <= now:
        raise LostLease()
    return row


def complete(db, job_id, token, kind, payload):
    with db.transaction():
        owned(db, job_id, token)
        db.execute("""INSERT INTO processing.job_results(job_id,attempt_id,kind,payload)
            SELECT job_id,id,%s,%s FROM processing.job_attempts WHERE job_id=%s AND token=%s""",
                   (kind, Jsonb(payload), job_id, token))
        db.execute("""UPDATE processing.job_attempts SET finished_at=clock_timestamp(),outcome='completed'
            WHERE job_id=%s AND token=%s""", (job_id, token))
        db.execute("""UPDATE processing.email_jobs SET state='completed',lease_token=NULL,
            lease_expires_at=NULL,last_error=NULL WHERE id=%s""", (job_id,))


def heartbeat(db, job_id, token, lease_seconds=180):
    if not 1 <= lease_seconds <= 3600:
        raise ValueError('Invalid lease')
    with db.transaction():
        owned(db, job_id, token)
        db.execute("""UPDATE processing.email_jobs SET lease_expires_at=clock_timestamp()+%s*interval '1 second'
            WHERE id=%s""", (lease_seconds, job_id))


def backoff(attempt):
    return random.uniform(0, min(900, 30 * 2 ** min(attempt-1, 10)))


def transition_failure(db, row, outcome, code):
    dead = outcome == 'permanent' or row['attempts'] >= row['attempt_limit']
    db.execute("""UPDATE processing.job_attempts SET finished_at=clock_timestamp(),outcome=%s,error_code=%s
        WHERE job_id=%s AND token=%s AND finished_at IS NULL""",
               (outcome, code, row['id'], row['lease_token']))
    db.execute("""UPDATE processing.email_jobs SET state=%s,lease_token=NULL,lease_expires_at=NULL,
        last_error=%s,due_at=clock_timestamp()+%s*interval '1 second' WHERE id=%s""",
               ('dead' if dead else 'retry_wait', code, backoff(row['attempts']), row['id']))


def fail(db, job_id, token, permanent=False, code=None):
    if code is not None and not re.fullmatch(r'[a-z][a-z0-9_]{0,79}',code):
        raise ValueError('Invalid failure code')
    with db.transaction():
        row = owned(db, job_id, token)
        transition_failure(db, row, 'permanent' if permanent else 'transient',
                           code or ('processor_permanent' if permanent else 'processor_transient'))


def recover(db, limit=100):
    with db.transaction():
        rows = db.execute("""SELECT * FROM processing.email_jobs WHERE state='leased'
            AND lease_expires_at<=clock_timestamp() ORDER BY lease_expires_at
            FOR UPDATE SKIP LOCKED LIMIT %s""", (limit,)).fetchall()
        for row in rows:
            transition_failure(db, row, 'abandoned', 'lease_expired')
        return len(rows)
