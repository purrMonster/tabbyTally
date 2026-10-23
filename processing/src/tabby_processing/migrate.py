import hashlib
import json
from pathlib import Path

DIRECTORY = Path(__file__).parent / 'migrations'


def structure(db):
    """Deterministic structure, excluding grants/owners and data."""
    queries = [
        """SELECT c.relname,a.attname,a.attnum,format_type(a.atttypid,a.atttypmod) AS type,
        a.attnotnull,pg_get_expr(d.adbin,d.adrelid) AS default_value
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname='processing' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY c.relname,a.attnum""",
        """SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) AS definition
        FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='processing'
        ORDER BY c.relname,k.conname""",
        "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='processing' ORDER BY tablename,indexname",
    ]
    return hashlib.sha256(json.dumps([db.execute(q).fetchall() for q in queries],
                                    sort_keys=True).encode()).hexdigest()


def migrate(db, status=False):
    files = sorted(DIRECTORY.glob('*.sql'))
    with db.transaction():
        db.execute("SET LOCAL search_path=pg_catalog")
        db.execute('SELECT pg_advisory_xact_lock(734293)')
        exists = db.execute("SELECT to_regclass('processing.schema_migrations') AS name").fetchone()['name']
        rows = db.execute('SELECT * FROM processing.schema_migrations ORDER BY id').fetchall() if exists else []
        if exists and not rows:
            raise ValueError('Empty migration history')
        if len(rows) > len(files):
            raise ValueError('Unknown migration')
        for index, file in enumerate(files, 1):
            if int(file.name[:3]) != index:
                raise ValueError('Migration sequence invalid')
            digest = hashlib.sha256(file.read_text(encoding='utf-8').encode()).hexdigest()
            if index <= len(rows) and (rows[index-1]['id'] != index or rows[index-1]['sha256'] != digest):
                raise ValueError('Migration checksum differs')
        if rows and rows[-1]['schema_sha256'] != structure(db):
            raise ValueError('Schema drift')
        if not status:
            for index, file in enumerate(files[len(rows):], len(rows)+1):
                source = file.read_text(encoding='utf-8')
                db.execute(source)
                db.execute('INSERT INTO processing.schema_migrations(id,sha256,schema_sha256) VALUES (%s,%s,%s)',
                           (index, hashlib.sha256(source.encode()).hexdigest(), structure(db)))
        return {'applied': len(rows) if status else len(files), 'available': len(files)}


def compatible(db):
    # Runtime role does not acquire migration locks or read privileged catalog data.
    rows = db.execute('SELECT id,sha256 FROM processing.schema_migrations ORDER BY id').fetchall()
    expected = [{'id': i, 'sha256': hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()}
                for i, p in enumerate(sorted(DIRECTORY.glob('*.sql')), 1)]
    if rows != expected:
        raise ValueError('Incompatible schema')
