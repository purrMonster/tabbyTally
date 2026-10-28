"""Explicit role provisioning; never called by runtime startup."""
from psycopg import sql

ROLES = ('processing_runtime', 'processing_operator', 'processing_inspector', 'processing_extractor','processing_reviewer')


def provision(db):
    with db.transaction():
        for role in ROLES:
            existing = db.execute('SELECT oid,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s', (role,)).fetchone()
            if existing:
                if any(existing[k] for k in ('rolsuper','rolcreatedb','rolcreaterole','rolreplication','rolbypassrls')):
                    raise ValueError('Unsafe existing role')
                if db.execute('SELECT 1 FROM pg_auth_members WHERE member=%s', (existing['oid'],)).fetchone():
                    raise ValueError('Role memberships require manual inspection')
                if db.execute('SELECT 1 FROM pg_shdepend WHERE refobjid=%s AND deptype=%s LIMIT 1', (existing['oid'], 'o')).fetchone():
                    raise ValueError('Role ownership requires manual inspection')
            else:
                db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
            ident = sql.Identifier(role)
            db.execute(sql.SQL('REVOKE ALL ON SCHEMA processing,imap_receiver FROM {}').format(ident))
            db.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA processing,imap_receiver FROM {}').format(ident))
            db.execute(sql.SQL('GRANT USAGE ON SCHEMA processing,imap_receiver TO {}').format(ident))
            db.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA processing TO {}').format(ident))
            db.execute(sql.SQL('GRANT SELECT(id,mailbox_id,uid_validity,uid,capture_status,raw_sha256) ON imap_receiver.emails TO {}').format(ident))
            db.execute(sql.SQL('GRANT SELECT(id,uid_validity,last_uid,initialized_at) ON imap_receiver.mailboxes TO {}').format(ident))
        db.execute('GRANT INSERT,UPDATE ON processing.email_jobs,processing.job_attempts TO processing_runtime')
        db.execute('GRANT INSERT ON processing.job_results TO processing_runtime')
        db.execute('GRANT INSERT ON processing.pipeline_versions,processing.processing_runs,processing.run_mailbox_boundaries,processing.run_email_selections,processing.operator_actions TO processing_operator')
        db.execute('GRANT UPDATE(enabled) ON processing.processing_runs TO processing_operator')
        db.execute('GRANT UPDATE(state,attempt_limit,due_at) ON processing.email_jobs TO processing_operator')
        db.execute('GRANT SELECT(subject,text_body,html_body,message_date) ON imap_receiver.emails TO processing_extractor')
        db.execute('GRANT INSERT ON processing.extraction_results,processing.transaction_candidates TO processing_extractor')
        db.execute('GRANT INSERT ON processing.reviews,processing.notification_outbox TO processing_extractor')
        db.execute('GRANT UPDATE ON processing.reviews,processing.transaction_candidates,processing.notification_outbox TO processing_reviewer')
        db.execute('GRANT INSERT ON processing.review_decisions,processing.action_receipts,processing.notification_outbox TO processing_reviewer')
        db.execute('GRANT INSERT ON processing.transaction_candidates TO processing_reviewer')
        db.execute('GRANT INSERT ON processing.logical_accounts,processing.account_mappings TO processing_operator')
        # NOLOGIN group roles: deployment supplies separate login credentials locally.
        # PUBLIC privileges must not undermine source-column isolation.
        for role in ROLES:
            for table in ('accounts','emails','mailboxes'):
                if db.execute('SELECT has_table_privilege(%s,%s,%s) AS allowed',
                              (role, 'imap_receiver.'+table, 'UPDATE')).fetchone()['allowed']:
                    raise ValueError('Inherited source UPDATE privilege')
            if db.execute("SELECT has_column_privilege(%s,'imap_receiver.accounts','credential_ref','SELECT') AS allowed", (role,)).fetchone()['allowed']:
                raise ValueError('Inherited credential access')
            for column in ('text_body','html_body','raw_email'):
                if role=='processing_extractor' and column!='raw_email':
                    continue
                if db.execute("SELECT has_column_privilege(%s,'imap_receiver.emails',%s,'SELECT') AS allowed", (role,column)).fetchone()['allowed']:
                    raise ValueError('Unexpected source content access')
            if db.execute("SELECT has_schema_privilege(%s,'processing','CREATE') AS allowed", (role,)).fetchone()['allowed']:
                raise ValueError('Unexpected schema creation access')
