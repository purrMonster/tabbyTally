import { ImapFlow } from 'imapflow';
import pg from 'pg';
import { randomUUID } from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';
import { nextRange } from './checkpoint.js';

for (const key of ['DATABASE_URL', 'IMAP_USER', 'IMAP_PASSWORD', 'N8N_WEBHOOK_URL', 'WEBHOOK_TOKEN']) {
  if (!process.env[key]) throw new Error(`Missing ${key}`);
}
const webhook = new URL(process.env.N8N_WEBHOOK_URL);
if (webhook.protocol !== 'https:') throw new Error('Webhook must use HTTPS');
const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
const db = await pool.connect();
// One process owns this database's listener tables. Never run multiple replicas.
const ownership = await db.query('SELECT pg_try_advisory_lock(734291) AS acquired');
if (!ownership.rows[0].acquired) throw new Error('Another listener is already running');
db.on('error', () => process.exit(1));
await db.query(`
  CREATE TABLE IF NOT EXISTS mail_checkpoint (
    mailbox_key text PRIMARY KEY, uid_validity text NOT NULL, last_uid bigint NOT NULL
  );
  CREATE TABLE IF NOT EXISTS mail_event (
    event_id uuid PRIMARY KEY, mailbox_key text NOT NULL,
    uid_validity text NOT NULL, uid bigint NOT NULL, raw_email bytea NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz,
    attempts integer NOT NULL DEFAULT 0, next_attempt timestamptz NOT NULL DEFAULT now(),
    UNIQUE(mailbox_key, uid_validity, uid)
  );
`);
const mailbox = process.env.IMAP_MAILBOX || 'INBOX';
const host = process.env.IMAP_HOST || 'imap.purelymail.com';
const key = `${host}/${process.env.IMAP_USER}/${mailbox}`;
let stopping = false;
let client;
const log = (event) => console.log(JSON.stringify({ time: new Date().toISOString(), event }));
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => {
  stopping = true;
  client?.close();
});

async function capture() {
  const lock = await client.getMailboxLock(mailbox, { readOnly: true });
  try {
    const result = await db.query('SELECT * FROM mail_checkpoint WHERE mailbox_key=$1', [key]);
    const state = result.rows[0];
    const next = nextRange(state, client.mailbox);
    if (!state) {
      await db.query('INSERT INTO mail_checkpoint VALUES ($1,$2,$3)', [key, next.validity, next.last]);
      log('new_mail_checkpoint_created');
      return;
    }
    if (!next.range) return;
    // Bounded UID ranges avoid IMAP's surprising N:* behavior on empty tails.
    for await (const message of client.fetch(next.range, { uid: true, source: true }, { uid: true })) {
      if (!message.source) throw new Error('Missing message source');
      await db.query('BEGIN');
      try {
        await db.query(`INSERT INTO mail_event
          (event_id,mailbox_key,uid_validity,uid,raw_email) VALUES ($1,$2,$3,$4,$5)
          ON CONFLICT (mailbox_key,uid_validity,uid) DO NOTHING`,
        [randomUUID(), key, next.validity, message.uid, message.source]);
        // Advance to the scan boundary only AFTER all returned messages are durable.
        await db.query('COMMIT');
      } catch (error) {
        await db.query('ROLLBACK');
        throw error;
      }
    }
    await db.query('UPDATE mail_checkpoint SET last_uid=$2 WHERE mailbox_key=$1', [key, next.end]);
    log('mail_capture_completed');
  } finally { lock.release(); }
}

async function listen() {
  while (!stopping) {
    let timer;
    let pending = Promise.resolve();
    let dirty = false;
    let running = false;
    client = new ImapFlow({ host, port: 993, secure: true,
      auth: { user: process.env.IMAP_USER, pass: process.env.IMAP_PASSWORD },
      logger: false, maxIdleTime: 240000 });
    const current = client;
    let closed;
    const done = new Promise(resolve => { closed = resolve; });
    current.on('close', closed);
    current.on('error', () => { log('imap_connection_error'); current.close(); closed(); });
    const requestScan = () => {
      dirty = true;
      if (running) return;
      running = true;
      pending = (async () => {
        try {
          while (dirty && !stopping && current.usable) {
            dirty = false;
            await capture();
          }
        } catch (error) {
          log(error.message.startsWith('UIDVALIDITY') ? 'uidvalidity_changed_manual_reconciliation_required' : 'capture_failed');
          current.close();
          closed();
        } finally { running = false; }
      })();
    };
    try {
      await current.connect();
      await current.mailboxOpen(mailbox, { readOnly: true });
      current.on('exists', requestScan);
      requestScan();
      // Safety reconciliation; IDLE notifications drive normal ingestion.
      timer = setInterval(requestScan, 60000);
      await done;
    } catch { log('imap_reconnect_pending'); }
    finally {
      clearInterval(timer);
      current.close();
      await pending;
    }
    if (!stopping) await sleep(5000);
  }
}

async function deliver() {
  while (!stopping) {
    try {
      const { rows } = await pool.query(`SELECT event_id, attempts FROM mail_event
        WHERE delivered_at IS NULL AND next_attempt <= now() ORDER BY received_at LIMIT 1`);
      if (!rows.length) { await sleep(1000); continue; }
      const row = rows[0];
      try {
        const response = await fetch(webhook, {
          method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15000),
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${process.env.WEBHOOK_TOKEN}` },
          body: JSON.stringify({ event_id: row.event_id, type: 'bank_email.received', schema_version: 1 })
        });
        await response.body?.cancel();
        if (!response.ok) throw new Error('Webhook rejected');
        await pool.query('UPDATE mail_event SET delivered_at=now() WHERE event_id=$1', [row.event_id]);
      } catch {
        const delay = Math.min(3600, 5 * 2 ** Math.min(row.attempts, 10));
        await pool.query(`UPDATE mail_event SET attempts=attempts+1,
          next_attempt=now()+($2 * interval '1 second') WHERE event_id=$1`, [row.event_id, delay]);
        log('webhook_retry_scheduled');
      }
    } catch { log('delivery_database_error'); await sleep(5000); }
  }
}
await Promise.all([listen(), deliver()]);
db.release();
await pool.end();
