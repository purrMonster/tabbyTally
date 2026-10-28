"""Snapshot-consistent receiver archives and isolated restore verification.

Only locally generated, trusted archives are supported. Never restores into a
caller-supplied database; the only restore destination is created by this process.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from psycopg import sql
from .database import connect

ROOT = Path('/backups')
TABLES = ('accounts', 'attachments', 'emails', 'mailboxes')
NAME = re.compile(r'receiver_\d{8}T\d{6}Z_[0-9a-f]{32}\.dump')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def archive_path(name):
    if not NAME.fullmatch(name):
        raise ValueError('Invalid archive filename')
    path = ROOT / name
    if path.is_symlink() or path.resolve().parent != ROOT.resolve():
        raise ValueError('Archive must be a local file in backups')
    return path


def run_pg(arguments):
    # No shell, password arguments, or SQL/server errors in user-visible output.
    result = subprocess.run(arguments, capture_output=True, timeout=1800, check=False)
    if result.returncode or result.stderr.strip():
        raise RuntimeError('PostgreSQL tool failed or emitted warnings; archive not verified')


def write_json(path, data):
    # Exclusive writes ensure an earlier verification record is never overwritten.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def fingerprint(db, include_migrations=True):
    """Compare the supported four-table schema and every row, including checkpoints."""
    db.execute("SET LOCAL timezone = 'UTC'")
    db.execute("SET LOCAL bytea_output = 'hex'")
    db.execute("SET LOCAL search_path = pg_catalog")
    tables = db.execute("""SELECT c.relname AS name FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='imap_receiver' AND c.relkind IN ('r','p') ORDER BY 1""").fetchall()
    names = tuple(row['name'] for row in tables)
    if names not in (TABLES, TABLES + ('schema_migrations',)):
        raise ValueError('Unsupported receiver table layout; update verifier before backup')
    columns = db.execute("""SELECT c.relname, a.attname, a.attnum,
        format_type(a.atttypid,a.atttypmod) AS type, a.attnotnull,
        pg_get_expr(d.adbin,d.adrelid) AS default_value, a.attidentity, a.attgenerated
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname='imap_receiver' AND c.relkind IN ('r','p')
        AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""").fetchall()
    constraints = db.execute("""SELECT c.relname, k.conname,
        pg_get_constraintdef(k.oid) AS definition FROM pg_constraint k
        JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='imap_receiver' ORDER BY c.relname,k.conname""").fetchall()
    indexes = db.execute("""SELECT tablename,indexname,indexdef FROM pg_indexes
        WHERE schemaname='imap_receiver' ORDER BY tablename,indexname""").fetchall()
    structure = {'columns': columns, 'constraints': constraints, 'indexes': indexes}
    if not include_migrations:
        structure['columns'] = [row for row in columns if row['relname'] != 'schema_migrations']
        structure['constraints'] = [row for row in constraints if row['relname'] != 'schema_migrations']
        structure['indexes'] = [row for row in indexes if row['tablename'] != 'schema_migrations']
        names = TABLES
    result = {'schema_sha256': hashlib.sha256(json.dumps(structure, sort_keys=True).encode()).hexdigest(),
              'tables': {}}
    for table in names:
        digest = hashlib.sha256()
        count = 0
        # Stream rows rather than buffering the complete mailbox in Python memory.
        with db.cursor(name='backup_rows') as cursor:
            cursor.execute(sql.SQL('SELECT to_jsonb(t)::text AS row FROM {}.{} t ORDER BY id')
                           .format(sql.Identifier('imap_receiver'), sql.Identifier(table)))
            for row in cursor:
                encoded = row['row'].encode('utf-8')
                digest.update(len(encoded).to_bytes(8, 'big'))
                digest.update(encoded)
                count += 1
        result['tables'][table] = {'rows': count, 'sha256': digest.hexdigest()}
    invalid = db.execute("""SELECT count(*) AS count FROM imap_receiver.emails
        WHERE raw_email IS NOT NULL AND
        raw_sha256 IS DISTINCT FROM encode(sha256(raw_email), 'hex')""").fetchone()['count']
    if invalid:
        raise ValueError('Stored raw email hash mismatch')
    result['raw_hash_mismatches'] = invalid
    return result


def combined_fingerprint(db):
    from .processing_backup import fingerprint as processing_fingerprint
    return {'receiver': fingerprint(db), 'processing': processing_fingerprint(db)}


def create_backup(include_processing=False):
    ROOT.mkdir(parents=True, exist_ok=True)
    name = 'receiver_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex + '.dump'
    destination = archive_path(name)
    partial = destination.with_suffix('.dump.partial')
    # A manifest is the completion marker. Interrupted .partial files are not usable.
    with partial.open('xb'):
        pass
    with connect() as db, db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        snapshot = db.execute('SELECT pg_export_snapshot() AS snapshot').fetchone()['snapshot']
        expected = combined_fingerprint(db) if include_processing else fingerprint(db)
        schemas = ['--schema=processing'] if include_processing else []
        run_pg(['pg_dump', '--format=custom', '--schema=imap_receiver', *schemas, '--strict-names',
                '--no-password', '--lock-wait-timeout=10s', '--snapshot=' + snapshot,
                '--file=' + str(partial)])
    digest = digest_file(partial)
    partial.rename(destination)
    write_json(destination.with_suffix('.json'), {
        'format_version': 2 if include_processing else 1, 'created_at': now(), 'archive': name,
        'archive_sha256': digest, 'scope': 'imap_receiver + processing' if include_processing else 'imap_receiver schema', 'fingerprint': expected,
    })
    print(json.dumps({'event': 'backup_created', 'archive': name,
                      'scope': 'combined' if include_processing else 'receiver'}))
    return name


def verify_backup(name):
    archive = archive_path(name)
    manifest_path = archive.with_suffix('.json')
    if manifest_path.is_symlink():
        raise ValueError('Manifest cannot be a symlink')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    valid_scope = (manifest.get('format_version'), manifest.get('scope')) in (
        (1, 'imap_receiver schema'), (2, 'imap_receiver + processing'))
    if (not valid_scope or manifest.get('archive') != name
            or manifest.get('archive_sha256') != digest_file(archive)):
        raise ValueError('Archive integrity or manifest validation failed')
    target = 'imap_restorecheck_' + uuid.uuid4().hex
    created = False
    matched = False
    # CREATE DATABASE fails on collision: never reuse or remove an existing database.
    with connect() as admin:
        source = admin.execute('SELECT current_database() AS name').fetchone()['name']
        if target == source or not re.fullmatch(r'imap_restorecheck_[0-9a-f]{32}', target):
            raise ValueError('Unsafe restore target')
        try:
            admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(target)))
            created = True
            admin.execute(sql.SQL('REVOKE CONNECT ON DATABASE {} FROM PUBLIC').format(sql.Identifier(target)))
            run_pg(['pg_restore', '--no-password', '--exit-on-error', '--single-transaction',
                    '--no-owner', '--no-privileges', '--dbname=' + target, str(archive)])
            with connect(dbname=target) as restored, restored.transaction():
                restored.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                actual = combined_fingerprint(restored) if manifest['format_version'] == 2 else fingerprint(restored)
            if actual != manifest['fingerprint']:
                raise ValueError('Restored schema or row fingerprint differs from snapshot')
            matched = True
        finally:
            if created:
                # Exact name created above only. Never FORCE, never source, never user input.
                try:
                    admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(target)))
                except Exception:
                    print(json.dumps({'event': 'restore_cleanup_failed', 'temporary_database': target}),
                          file=sys.stderr)
                    raise
    if matched:
        report = archive.with_suffix('.verified.' + uuid.uuid4().hex + '.json')
        write_json(report, {'verified_at': now(), 'archive': name,
                            'archive_sha256': manifest['archive_sha256'],
                            'fingerprint': actual, 'temporary_database_removed': True})
        print(json.dumps({'event': 'restore_verified', 'archive': name,
                          'temporary_database_removed': True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='Create a consistent receiver-schema archive')
    create.add_argument('--verify', action='store_true', help='Also restore and verify the new archive')
    create.add_argument('--include-processing', action='store_true', help='Archive both schemas consistently; required for Phase 2')
    verify = commands.add_parser('verify', help='Verify a trusted local archive in a new disposable database')
    verify.add_argument('archive', help='Archive basename only, inside /backups')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == 'create':
            name = create_backup(include_processing=args.include_processing)
            if args.verify:
                verify_backup(name)
        else:
            verify_backup(args.archive)
    except Exception as error:
        print(json.dumps({'event': 'backup_failed', 'error_class': type(error).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
