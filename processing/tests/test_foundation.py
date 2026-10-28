"""Real PostgreSQL tests confined to a newly created disposable database per test."""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
from psycopg import sql
from tabby_processing import admin, discovery, jobs, migrate, worker
from tabby_processing.database import connect

RECEIVER = Path('/app/imap-receiver')
sys.path.insert(0, str(RECEIVER))
from src import backup


@unittest.skipUnless(os.environ.get('RUN_PROCESSING_TESTS') == '1', 'isolated PostgreSQL opt-in required')
class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.name = 'processing_test_' + uuid.uuid4().hex
        self.admin = connect()
        self.admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(self.name)))
        self.addCleanup(self.cleanup)
        self.db = connect(dbname=self.name)
        self.db.execute((RECEIVER/'migrations/001_initial.sql').read_text())
        migrate.migrate(self.db)
        account = self.db.execute("INSERT INTO imap_receiver.accounts(name,imap_host,username,credential_ref) VALUES ('synthetic','invalid','test','SECRET') RETURNING id").fetchone()['id']
        self.mailbox = self.db.execute("""INSERT INTO imap_receiver.mailboxes(account_id,uid_validity,last_uid,initialized_at)
            VALUES (%s,1,0,now()) RETURNING id""",(account,)).fetchone()['id']

    def cleanup(self):
        if hasattr(self,'db'):
            self.db.close()
        self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.name)))
        self.admin.close()

    def email(self, uid=1, db=None):
        db = db or self.db
        return db.execute("""INSERT INTO imap_receiver.emails(mailbox_id,uid_validity,uid,size_bytes,capture_status)
            VALUES (%s,1,%s,0,'oversized') RETURNING id""",(self.mailbox,uid)).fetchone()['id']

    def queued(self, config=None):
        email = self.email()
        self.run = discovery.activate(self.db,'fake-v1',email_ids=[email],config=config)
        discovery.reconcile(self.db)
        return self.db.execute('SELECT id FROM processing.email_jobs').fetchone()['id']

    def expire(self, job):
        self.db.execute("UPDATE processing.email_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",(job,))

    def due(self):
        self.db.execute("UPDATE processing.email_jobs SET due_at=clock_timestamp()-interval '1 second'")

    def test_migrations_and_drift(self):
        self.assertEqual(migrate.migrate(self.db)['applied'],len(list(migrate.DIRECTORY.glob('*.sql'))))
        migrate.compatible(self.db)
        self.db.execute('ALTER TABLE processing.email_jobs ADD COLUMN unexpected text')
        with self.assertRaises(ValueError): migrate.migrate(self.db)

    def test_checksum_rejected(self):
        self.db.execute("UPDATE processing.schema_migrations SET sha256='changed'")
        with self.assertRaises(ValueError): migrate.migrate(self.db)
        with self.assertRaises(ValueError): migrate.compatible(self.db)

    def test_discovery_activation_late_commit(self):
        self.email(1)
        self.db.execute('UPDATE imap_receiver.mailboxes SET last_uid=1')
        with connect(dbname=self.name) as capture:
            with capture.transaction():
                late = self.email(2,capture)
                capture.execute('UPDATE imap_receiver.mailboxes SET last_uid=2')
                discovery.activate(self.db,'live',mailbox_ids=[self.mailbox])
                self.assertEqual(discovery.reconcile(self.db)['inserted'],0)
            self.assertEqual(discovery.reconcile(self.db)['inserted'],1)
            self.assertEqual(discovery.reconcile(self.db)['inserted'],0)
            self.assertEqual(self.db.execute('SELECT email_id FROM processing.email_jobs').fetchone()['email_id'],late)
        self.db.execute('UPDATE imap_receiver.mailboxes SET uid_validity=2')
        self.assertEqual(discovery.reconcile(self.db)['uidvalidity_mismatches'],1)

    def test_concurrent_discovery_and_claim(self):
        email = self.email()
        discovery.activate(self.db,'v',email_ids=[email])
        def scan():
            with connect(dbname=self.name) as db: return discovery.reconcile(db)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _: scan(),range(2)))
        def claim():
            with connect(dbname=self.name) as db: return jobs.claim(db)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            claims = list(pool.map(lambda _: claim(),range(2)))
        self.assertEqual(sum(x is not None for x in claims),1)

    def test_completion_atomic_and_stale(self):
        job_id = self.queued()
        job = jobs.claim(self.db)
        with self.assertRaises(psycopg.errors.CheckViolation):
            jobs.complete(self.db,job_id,job['lease_token'],'invalid',{})
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM processing.job_results').fetchone()['n'],0)
        self.expire(job_id)
        for operation in (lambda: jobs.complete(self.db,job_id,job['lease_token'],'fake_success',{}),
                          lambda: jobs.heartbeat(self.db,job_id,job['lease_token']),
                          lambda: jobs.fail(self.db,job_id,job['lease_token'])):
            with self.assertRaises(jobs.LostLease): operation()
        self.assertEqual(jobs.recover(self.db),1)
        self.due()
        newer = jobs.claim(self.db)
        jobs.complete(self.db,job_id,newer['lease_token'],'fake_success',{})
        with self.assertRaises(jobs.LostLease): jobs.complete(self.db,job_id,job['lease_token'],'fake_success',{})
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM processing.job_results').fetchone()['n'],1)

    def test_retries_exhaustion_operator_pause(self):
        job_id = self.queued()
        discovery.set_enabled(self.db,self.run,False,'test pause')
        self.assertIsNone(jobs.claim(self.db))
        discovery.set_enabled(self.db,self.run,True,'test resume')
        for _ in range(5):
            self.due()
            job = jobs.claim(self.db)
            jobs.fail(self.db,job_id,job['lease_token'])
        self.assertEqual(self.db.execute('SELECT state FROM processing.email_jobs').fetchone()['state'],'dead')
        discovery.retry(self.db,job_id,1,'test recovery')
        self.assertEqual(jobs.claim(self.db)['attempts'],6)

    def test_fake_processor(self):
        self.queued({'scenario':'transient','failures':1})
        worker.once(self.db)
        self.due()
        worker.once(self.db)
        self.assertEqual(self.db.execute('SELECT kind FROM processing.job_results').fetchone()['kind'],'fake_review_required')

    def test_permissions(self):
        self.queued()
        admin.provision(self.db)
        with connect(dbname=self.name) as db:
            db.execute('SET ROLE processing_runtime')
            migrate.compatible(db)
            discovery.reconcile(db)
            job = jobs.claim(db)
            jobs.complete(db,job['id'],job['lease_token'],'fake_success',{})
            for query in ('UPDATE imap_receiver.emails SET uid=2',
                          'SELECT credential_ref FROM imap_receiver.accounts',
                          'SELECT text_body FROM imap_receiver.emails',
                          'CREATE TABLE processing.forbidden(id int)',
                          'UPDATE processing.processing_runs SET enabled=false',
                          'DELETE FROM processing.job_attempts'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege): db.execute(query)

    def test_process_crash_and_recovery(self):
        job_id = self.queued()
        script = "from tabby_processing.database import connect; from tabby_processing.jobs import claim; import time; db=connect(); claim(db); print('claimed',flush=True); time.sleep(120)"
        env = dict(os.environ,PGDATABASE=self.name)
        process = subprocess.Popen([sys.executable,'-c',script],env=env,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'claimed')
        finally:
            process.kill()
            process.wait(timeout=10)
            process.stdout.close()
        self.expire(job_id)
        self.assertEqual(jobs.recover(self.db),1)
        self.due()
        worker.once(self.db)
        self.assertEqual(self.db.execute('SELECT state FROM processing.email_jobs').fetchone()['state'],'completed')

    def test_commit_acknowledgement_lost(self):
        job_id = self.queued()
        job = jobs.claim(self.db)
        jobs.complete(self.db,job_id,job['lease_token'],'fake_success',{})
        with connect(dbname=self.name) as reconnected:
            self.assertEqual(reconnected.execute('SELECT state FROM processing.email_jobs WHERE id=%s',(job_id,)).fetchone()['state'],'completed')
            self.assertIsNone(jobs.claim(reconnected))

    def test_combined_backup_restore(self):
        self.queued()
        worker.once(self.db)
        with tempfile.TemporaryDirectory() as root, patch.object(backup,'ROOT',Path(root)), patch.dict(os.environ,PGDATABASE=self.name):
            archive = backup.create_backup(include_processing=True)
            backup.verify_backup(archive)
            self.assertEqual(len(list(Path(root).glob('*.verified.*.json'))),1)

    def test_capture_continues_with_failed_processing(self):
        sys.path.insert(0,str(RECEIVER/'tests'))
        from test_capture import FakeIMAP
        from src.capture import capture_once
        discovery.activate(self.db,'capture-failure',mailbox_ids=[self.mailbox],config={'scenario':'permanent'})
        @contextmanager
        def opener(_):
            yield FakeIMAP(),1
        captured = capture_once(self.db,{'id':self.mailbox},open_mailbox=opener,
            response_number=lambda _,name: 1 if name=='UIDVALIDITY' else 2,error=RuntimeError)
        before = self.db.execute('SELECT * FROM imap_receiver.emails').fetchall()
        discovery.reconcile(self.db)
        worker.once(self.db)
        self.assertEqual(captured['inserted'],1)
        self.assertEqual(captured['unread_before'],captured['unread_after'])
        self.assertEqual(captured['seen_unchanged'],1)
        self.assertEqual(self.db.execute('SELECT * FROM imap_receiver.emails').fetchall(),before)
        self.assertEqual(self.db.execute('SELECT last_uid FROM imap_receiver.mailboxes').fetchone()['last_uid'],1)
        self.assertEqual(self.db.execute('SELECT state FROM processing.email_jobs').fetchone()['state'],'dead')

    def test_crash_during_save_rolls_back(self):
        job_id = self.queued()
        script = '''from tabby_processing.database import connect
from tabby_processing import jobs
import time
db=connect()
j=jobs.claim(db)
with db.transaction():
    jobs.complete(db,j['id'],j['lease_token'],'fake_success',{})
    print('saving',flush=True)
    time.sleep(120)
'''
        process = subprocess.Popen([sys.executable,'-c',script],env=dict(os.environ,PGDATABASE=self.name),stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'saving')
        finally:
            process.kill()
            process.wait(timeout=10)
            process.stdout.close()
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM processing.job_results').fetchone()['n'],0)
        self.expire(job_id)
        jobs.recover(self.db)
        self.due()
        worker.once(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM processing.job_results').fetchone()['n'],1)

    def test_concurrent_recovery_and_post_reclaim_fence(self):
        job_id = self.queued()
        old = jobs.claim(self.db)
        self.expire(job_id)
        def recover():
            with connect(dbname=self.name) as db: return jobs.recover(db)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(lambda _:recover(),range(2))),1)
        self.due()
        new = jobs.claim(self.db)
        for fn in (lambda:jobs.complete(self.db,job_id,old['lease_token'],'fake_success',{}),
                   lambda:jobs.fail(self.db,job_id,old['lease_token']),
                   lambda:jobs.heartbeat(self.db,job_id,old['lease_token'])):
            with self.assertRaises(jobs.LostLease): fn()
        jobs.complete(self.db,job_id,new['lease_token'],'fake_success',{})

    def test_restore_all_states_and_runtime_permissions(self):
        ids = [self.email(i) for i in range(1,6)]
        discovery.activate(self.db,'states',email_ids=ids)
        discovery.reconcile(self.db)
        first = jobs.claim(self.db)
        jobs.complete(self.db,first['id'],first['lease_token'],'fake_success',{})
        second = jobs.claim(self.db)
        jobs.fail(self.db,second['id'],second['lease_token'],permanent=True)
        third = jobs.claim(self.db)
        jobs.fail(self.db,third['id'],third['lease_token'])
        # Keep retry_wait out of the way for deterministic remaining claims.
        self.db.execute("UPDATE processing.email_jobs SET due_at=clock_timestamp()+interval '1 hour' WHERE state='retry_wait'")
        leased = jobs.claim(self.db)
        target = 'processing_restore_' + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as root, patch.object(backup,'ROOT',Path(root)), patch.dict(os.environ,PGDATABASE=self.name):
            archive = backup.create_backup(include_processing=True)
            self.admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(target)))
            try:
                backup.run_pg(['pg_restore','--no-password','--exit-on-error','--single-transaction',
                    '--no-owner','--no-privileges','--dbname='+target,str(Path(root)/archive)])
                with connect(dbname=target) as restored:
                    with restored.transaction():
                        actual = backup.combined_fingerprint(restored)
                    import json
                    self.assertEqual(actual,json.loads((Path(root)/archive).with_suffix('.json').read_text())['fingerprint'])
                    self.assertEqual({r['state'] for r in restored.execute('SELECT state FROM processing.email_jobs')},
                                     {'queued','leased','retry_wait','completed','dead'})
                    admin.provision(restored)
                    discovery.invalidate_leases(restored,'test restore; old workers fenced')
                    restored.execute('SET ROLE processing_runtime')
                    jobs.recover(restored)
                    with self.assertRaises(jobs.LostLease): jobs.complete(restored,leased['id'],leased['lease_token'],'fake_success',{})
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege): restored.execute('UPDATE imap_receiver.emails SET uid=0')
                    self.assertEqual(discovery.reconcile(restored)['inserted'],0)
                    worker.once(restored)
            finally:
                self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(target)))

    def test_empty_backup_and_corruption(self):
        with tempfile.TemporaryDirectory() as root, patch.object(backup,'ROOT',Path(root)), patch.dict(os.environ,PGDATABASE=self.name):
            name = backup.create_backup(include_processing=True)
            backup.verify_backup(name)
            (Path(root)/name).write_bytes(b'corrupt')
            with self.assertRaises(ValueError): backup.verify_backup(name)

    def test_operator_and_inspector_roles(self):
        admin.provision(self.db)
        email = self.email()
        with connect(dbname=self.name) as db:
            db.execute('SET ROLE processing_operator')
            run = discovery.activate(db,'operator',email_ids=[email])
            discovery.set_enabled(db,run,False,'operator test')
            db.execute('SET ROLE processing_inspector')
            self.assertEqual(db.execute('SELECT count(*) AS n FROM processing.operator_actions').fetchone()['n'],2)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege): discovery.set_enabled(db,run,True,'forbidden')

    def test_connection_loss_preserves_claim(self):
        job_id = self.queued()
        with connect(dbname=self.name) as disconnected:
            job = jobs.claim(disconnected)
            pid = disconnected.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
            self.db.execute('SELECT pg_terminate_backend(%s)',(pid,))
            with self.assertRaises(psycopg.OperationalError):
                jobs.complete(disconnected,job_id,job['lease_token'],'fake_success',{})
        self.assertEqual(self.db.execute('SELECT state FROM processing.email_jobs').fetchone()['state'],'leased')
        self.expire(job_id)
        jobs.recover(self.db)
        self.due()
        with connect(dbname=self.name) as reconnected: worker.once(reconnected)
        self.assertEqual(self.db.execute('SELECT state FROM processing.email_jobs').fetchone()['state'],'completed')

    def test_crash_after_fake_processing_before_save(self):
        job_id = self.queued()
        script = '''from tabby_processing.database import connect
from tabby_processing import worker,jobs
import time
def interrupted(*args):
    print('processed',flush=True)
    time.sleep(120)
jobs.complete=interrupted
with connect() as db: worker.once(db)
'''
        process = subprocess.Popen([sys.executable,'-c',script],env=dict(os.environ,PGDATABASE=self.name),stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'processed')
        finally:
            process.kill()
            process.wait(timeout=10)
            process.stdout.close()
        self.expire(job_id)
        jobs.recover(self.db)
        self.due()
        worker.once(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM processing.job_results').fetchone()['n'],1)

    def test_backoff_and_bounded_fake_timeout(self):
        for attempt in range(1,30):
            self.assertGreaterEqual(jobs.backoff(attempt),0)
            self.assertLessEqual(jobs.backoff(attempt),min(900,30*2**min(attempt-1,10)))
        self.queued({'scenario':'delay','delay':1})
        worker.once(self.db,lease_seconds=2,deadline=0.01)
        self.assertEqual(self.db.execute('SELECT state FROM processing.email_jobs').fetchone()['state'],'retry_wait')
        self.db.execute("UPDATE processing.email_jobs SET due_at=clock_timestamp()+interval '1 hour'")
        self.assertIsNone(jobs.claim(self.db))


if __name__ == '__main__': unittest.main()
