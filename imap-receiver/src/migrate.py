"""Explicit, transactional schema setup and checked adoption of the legacy schema."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from .backup import fingerprint
from .database import connect

DIRECTORY = Path(__file__).resolve().parent.parent / 'migrations'
LOCK = 734292
LEDGER = '''CREATE TABLE imap_receiver.schema_migrations (
    id integer PRIMARY KEY,
    name text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now(),
    adopted boolean NOT NULL DEFAULT false
)'''


def load_migrations():
    migrations = []
    for path in sorted(DIRECTORY.glob('*.sql')):
        if not re.fullmatch(r'\d{3}_[a-z0-9_]+\.sql', path.name):
            raise ValueError('Invalid migration filename')
        # Normalize CRLF so Windows checkouts and Linux builds agree on checksums.
        source = path.read_text(encoding='utf-8').replace('\r\n', '\n')
        metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        expected = metadata['schema_sha256']
        if not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid expected schema fingerprint')
        digest = hashlib.sha256((source + '\n' + expected).encode()).hexdigest()
        migrations.append(dict(id=int(path.name[:3]), name=path.name, source=source,
                               sha256=digest, expected=expected))
    if not migrations or [m['id'] for m in migrations] != list(range(1, len(migrations) + 1)):
        raise ValueError('Migration sequence must start at 001 without gaps')
    return migrations


def inspect(db, migrations):
    exists = db.execute("SELECT to_regnamespace('imap_receiver') IS NOT NULL AS present").fetchone()['present']
    if not exists:
        return 'empty', []
    ledger = db.execute("SELECT to_regclass('imap_receiver.schema_migrations') IS NOT NULL AS present").fetchone()['present']
    if not ledger:
        if fingerprint(db, include_migrations=False)['schema_sha256'] != migrations[0]['expected']:
            raise ValueError('Legacy schema differs from baseline; no adoption allowed')
        return 'unversioned', []
    rows = db.execute('SELECT id,name,sha256 FROM imap_receiver.schema_migrations ORDER BY id').fetchall()
    if not rows or len(rows) > len(migrations):
        raise ValueError('Unknown or empty migration history')
    for applied, expected in zip(rows, migrations):
        if any(applied[key] != expected[key] for key in ('id', 'name', 'sha256')):
            raise ValueError('Migration history or checksum differs')
    if fingerprint(db, include_migrations=False)['schema_sha256'] != migrations[len(rows)-1]['expected']:
        raise ValueError('Database schema drift detected')
    return 'versioned', rows


def migrate(db, *, adopt_existing=False, status_only=False):
    migrations = load_migrations()
    with db.transaction():
        db.execute("SET LOCAL lock_timeout = '5s'")
        db.execute("SET LOCAL statement_timeout = '60s'")
        if not status_only:
            if not db.execute('SELECT pg_try_advisory_xact_lock(%s) AS locked', (LOCK,)).fetchone()['locked']:
                raise ValueError('Another migration is running')
        state, rows = inspect(db, migrations)
        if status_only:
            return {'state': state, 'applied': len(rows), 'available': len(migrations)}
        if state == 'unversioned' and not adopt_existing:
            raise ValueError('Existing unversioned schema requires --adopt-existing')
        adopted = state == 'unversioned'
        for migration in migrations[len(rows):]:
            if not (adopted and migration['id'] == 1):
                db.execute(migration['source'])
            if migration['id'] == 1:
                db.execute(LEDGER)
            if fingerprint(db, include_migrations=False)['schema_sha256'] != migration['expected']:
                raise ValueError('Migration result differs from expected schema')
            db.execute('''INSERT INTO imap_receiver.schema_migrations (id,name,sha256,adopted)
                VALUES (%s,%s,%s,%s)''', (migration['id'], migration['name'], migration['sha256'],
                                         adopted and migration['id'] == 1))
        return {'state': 'current', 'applied_now': len(migrations)-len(rows), 'version': len(migrations),
                'adopted': adopted}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'apply'))
    parser.add_argument('--adopt-existing', action='store_true')
    args = parser.parse_args()
    try:
        with connect() as db:
            result = migrate(db, adopt_existing=args.adopt_existing, status_only=args.command == 'status')
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({'event': 'migration_failed', 'error_class': type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
