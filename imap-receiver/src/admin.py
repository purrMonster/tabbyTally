"""Explicit administrator-only provisioning; never run by observer startup."""

import os
from pathlib import Path
import sys

from psycopg import sql
from .database import connect

ROLE = 'imap_receiver_runtime'


def provision():
    password = Path(os.environ['RUNTIME_PASSWORD_FILE']).read_bytes().decode('utf-8')
    if len(password) < 32 or not password.isascii() or not password.isalnum():
        raise ValueError('Runtime password must be at least 32 ASCII alphanumeric characters')
    with connect() as db, db.transaction():
        exists = db.execute('SELECT oid FROM pg_roles WHERE rolname=%s', (ROLE,)).fetchone()
        if exists:
            membership = db.execute('SELECT 1 FROM pg_auth_members WHERE member=%s', (exists['oid'],)).fetchone()
            ownership = db.execute("""SELECT 1 FROM pg_class WHERE relowner=%s
                UNION ALL SELECT 1 FROM pg_namespace WHERE nspowner=%s
                UNION ALL SELECT 1 FROM pg_database WHERE datdba=%s LIMIT 1""",
                (exists['oid'], exists['oid'], exists['oid'])).fetchone()
            if membership or ownership:
                raise ValueError('Existing runtime role has memberships or ownership; inspect manually')
        else:
            db.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(ROLE)))
        db.execute("SET LOCAL password_encryption = 'scram-sha-256'")
        db.execute(sql.SQL('ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}')
                   .format(sql.Identifier(ROLE), sql.Literal(password)))
        database = db.execute('SELECT current_database() AS name').fetchone()['name']
        db.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(database), sql.Identifier(ROLE)))
        db.execute(sql.SQL('REVOKE ALL ON SCHEMA imap_receiver FROM {}').format(sql.Identifier(ROLE)))
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA imap_receiver TO {}').format(sql.Identifier(ROLE)))
        db.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA imap_receiver FROM {}').format(sql.Identifier(ROLE)))
        db.execute(sql.SQL('REVOKE ALL ON ALL SEQUENCES IN SCHEMA imap_receiver FROM {}').format(sql.Identifier(ROLE)))
        db.execute(sql.SQL('GRANT SELECT ON imap_receiver.accounts, imap_receiver.mailboxes, imap_receiver.emails, imap_receiver.attachments TO {}')
                   .format(sql.Identifier(ROLE)))
        db.execute(sql.SQL('GRANT INSERT ON imap_receiver.emails, imap_receiver.attachments TO {}').format(sql.Identifier(ROLE)))
        db.execute(sql.SQL('GRANT UPDATE (uid_validity, last_uid, initialized_at, last_scan_at, last_error_code) ON imap_receiver.mailboxes TO {}')
                   .format(sql.Identifier(ROLE)))
    print('Runtime role provisioned. No account, checkpoint, or email rows changed.')


if __name__ == '__main__':
    try:
        provision()
    except Exception as error:
        # Never expose SQL text, exception details, or generated credentials.
        print(f'Provisioning failed: {type(error).__name__}', file=sys.stderr)
        sys.exit(1)
