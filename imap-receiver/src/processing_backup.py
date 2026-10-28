"""Additional verifier; receiver migration fingerprints remain unchanged."""
import hashlib
import json
from psycopg import sql

TABLES = ('email_jobs','job_attempts','job_results','operator_actions','pipeline_versions',
          'processing_runs','run_email_selections','run_mailbox_boundaries','schema_migrations')
EXTRACTION_TABLES = tuple(sorted(TABLES + ('logical_accounts','account_mappings','extraction_results','transaction_candidates')))
REVIEW_TABLES = tuple(sorted(EXTRACTION_TABLES + ('reviews','review_decisions','action_receipts','notification_outbox')))


def fingerprint(db):
    db.execute("SET LOCAL search_path=pg_catalog")
    db.execute("SET LOCAL timezone='UTC'")
    names = tuple(r['name'] for r in db.execute("""SELECT c.relname AS name FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='processing'
        AND c.relkind IN ('r','p','v','m','S','f') ORDER BY 1""").fetchall())
    if names not in (TABLES, EXTRACTION_TABLES, REVIEW_TABLES):
        raise ValueError('Unsupported processing layout')
    if db.execute("SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='processing' LIMIT 1").fetchone():
        raise ValueError('Unsupported processing functions')
    if db.execute("""SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='processing' AND NOT t.tgisinternal LIMIT 1""").fetchone():
        raise ValueError('Unsupported processing triggers')
    columns = db.execute("""SELECT c.relname,a.attname,a.attnum,format_type(a.atttypid,a.atttypmod) AS type,
        a.attnotnull,pg_get_expr(d.adbin,d.adrelid) AS default_value
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname='processing' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""").fetchall()
    constraints = db.execute("""SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) AS definition
        FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='processing' ORDER BY c.relname,k.conname""").fetchall()
    indexes = db.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='processing' ORDER BY tablename,indexname").fetchall()
    result = {'schema_sha256': hashlib.sha256(json.dumps([columns,constraints,indexes], sort_keys=True).encode()).hexdigest(), 'tables': {}}
    for table in names:
        digest, count = hashlib.sha256(), 0
        with db.cursor(name='processing_backup_rows') as cursor:
            cursor.execute(sql.SQL('SELECT to_jsonb(t)::text AS row FROM processing.{} t ORDER BY id').format(sql.Identifier(table)))
            for row in cursor:
                encoded = row['row'].encode()
                digest.update(len(encoded).to_bytes(8,'big'))
                digest.update(encoded)
                count += 1
        result['tables'][table] = {'rows':count,'sha256':digest.hexdigest()}
    return result
