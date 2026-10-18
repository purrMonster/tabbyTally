"""Run receiver regressions in a newly created disposable database."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from psycopg import sql
from tabby_processing.database import connect

sys.path.insert(0,'/app/imap-receiver')
from src import migrate, admin


def main():
    name = 'receiver_regression_' + uuid.uuid4().hex
    with connect() as server:
        server.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        try:
            with connect(dbname=name) as db:
                migrate.migrate(db)
            with tempfile.TemporaryDirectory() as root:
                password = Path(root)/'password'
                password.write_text(uuid.uuid4().hex)
                original = dict(os.environ)
                try:
                    os.environ.update(PGDATABASE=name,RUNTIME_PASSWORD_FILE=str(password))
                    admin.provision()
                    env = dict(os.environ,RUN_DB_TESTS='1',RUN_ROLE_TESTS='1',RUN_MIGRATION_TESTS='1')
                    return subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],
                                          cwd='/app/imap-receiver',env=env).returncode
                finally:
                    os.environ.clear()
                    os.environ.update(original)
        finally:
            server.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


if __name__ == '__main__': raise SystemExit(main())
