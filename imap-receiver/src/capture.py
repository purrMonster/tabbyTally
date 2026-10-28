"""Bounded, explicit single-mailbox capture. No persistent worker yet."""

from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import hashlib
import imaplib
import re

from psycopg.types.json import Jsonb


def parse_source(raw):
    result = dict(subject=None, message_id=None, message_date=None,
                  from_addresses=[], to_addresses=[], cc_addresses=[],
                  text_body=None, html_body=None, capture_status='captured',
                  error_code=None, attachments=[])
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        for key in ('subject', 'message_id'):
            value = message.get(key.replace('_', '-'))
            result[key] = str(value) if value is not None else None
        for header in ('from', 'to', 'cc'):
            result[f'{header}_addresses'] = [
                {'name': name, 'address': address}
                for name, address in getaddresses([str(v) for v in message.get_all(header, [])])
            ]
        try:
            date = parsedate_to_datetime(str(message.get('Date', '')))
            result['message_date'] = date if date.tzinfo else None
        except (ValueError, TypeError, IndexError):
            pass
        for kind in ('plain', 'html'):
            body = message.get_body(preferencelist=(kind,))
            if body is not None:
                result['text_body' if kind == 'plain' else 'html_body'] = body.get_content()
        for index, part in enumerate(message.iter_attachments()):
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = part.as_bytes(policy=policy.default)
            result['attachments'].append(dict(
                part_index=index, filename=part.get_filename(),
                content_type=part.get_content_type(), size_bytes=len(payload),
                content_id=str(part['Content-ID']) if part['Content-ID'] else None,
                sha256=hashlib.sha256(payload).hexdigest()))
        if any(part.defects for part in message.walk()):
            result.update(capture_status='parse_failed', error_code='mime_defect')
    except Exception:
        result.update(capture_status='parse_failed', error_code='mime_parse_error')
    return result


def clean(value):
    # PostgreSQL text/jsonb cannot represent NUL. Original bytes remain untouched.
    if isinstance(value, str):
        return value.replace('\x00', '\ufffd')
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    return value


def metadata(client, uid, error):
    status, data = client.uid('FETCH', str(uid), '(UID RFC822.SIZE INTERNALDATE FLAGS)')
    if status != 'OK':
        raise error('Metadata fetch failed; capture rolled back.')
    line = next((item for item in data if isinstance(item, bytes) and b'RFC822.SIZE' in item), None)
    if not line:
        raise error('Message vanished during capture; checkpoint not advanced.')
    uid_match = re.search(rb'\bUID (\d+)', line)
    size_match = re.search(rb'RFC822.SIZE (\d+)', line)
    date_match = re.search(rb'INTERNALDATE "([^"]+)"', line)
    if not uid_match or int(uid_match[1]) != uid or not size_match or not date_match:
        raise error('Invalid metadata response; checkpoint not advanced.')
    date = datetime.strptime(date_match[1].decode('ascii').strip(), '%d-%b-%Y %H:%M:%S %z')
    return int(size_match[1]), date, b'\\Seen' in imaplib.ParseFlags(line)


def store_email(db, mailbox_id, validity, uid, size, date, raw, parsed):
    parsed = clean(parsed)
    row = db.execute("""
        INSERT INTO imap_receiver.emails
        (mailbox_id, uid_validity, uid, size_bytes, internal_date, raw_email,
         raw_sha256, subject, message_id, message_date, from_addresses,
         to_addresses, cc_addresses, text_body, html_body, capture_status,
         error_code, parser_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (mailbox_id, uid_validity, uid) DO NOTHING RETURNING id
    """, (mailbox_id, validity, uid, size, date, raw,
          hashlib.sha256(raw).hexdigest() if raw is not None else None,
          parsed['subject'], parsed['message_id'], parsed['message_date'],
          Jsonb(parsed['from_addresses']), Jsonb(parsed['to_addresses']), Jsonb(parsed['cc_addresses']),
          parsed['text_body'], parsed['html_body'], parsed['capture_status'],
          parsed['error_code'], 'stdlib-email-v1')).fetchone()
    if row:
        for attachment in parsed['attachments']:
            db.execute("""
                INSERT INTO imap_receiver.attachments
                (email_id, part_index, filename, content_type, size_bytes, content_id, sha256)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (row['id'], *(attachment[k] for k in
                  ('part_index', 'filename', 'content_type', 'size_bytes', 'content_id', 'sha256'))))
    return row is not None


def capture_once(db, target, *, open_mailbox, response_number, error,
                 limit=50, max_bytes=10 * 1024 * 1024):
    result = dict(examined=0, inserted=0, parse_failed=0, oversized=0,
                  seen_unchanged=0, unread_before=0, unread_after=0)
    with db.transaction():
        lock = db.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s::text, 0)) AS acquired',
                          (str(target['id']),)).fetchone()
        if not lock['acquired']:
            raise error('Mailbox is owned by another worker.')
        checkpoint = db.execute('SELECT * FROM imap_receiver.mailboxes WHERE id=%s FOR UPDATE',
                                (target['id'],)).fetchone()
        if not checkpoint or checkpoint['initialized_at'] is None:
            raise error('Initialize the mailbox before capturing; no baseline was created.')
        with open_mailbox(target) as (client, _):
            validity = response_number(client, 'UIDVALIDITY')
            end = response_number(client, 'UIDNEXT') - 1
            last = checkpoint['last_uid']
            if validity != checkpoint['uid_validity']:
                raise error('UIDVALIDITY changed; manual reconciliation required.')
            if end < last:
                raise error('UIDNEXT moved backwards; manual reconciliation required.')
            uids = []
            if last < end:
                status, data = client.uid('SEARCH', None, 'UID', f'{last + 1}:{end}')
                if status != 'OK':
                    raise error('UID search failed.')
                uids = sorted(set(int(v) for v in data[0].split()))
                if any(uid <= last or uid > end for uid in uids):
                    raise error('Server returned a UID outside the requested range.')
            selected = uids[:limit]
            for uid in selected:
                size, date, seen_before = metadata(client, uid, error)
                raw = None
                if size <= max_bytes:
                    status, parts = client.uid('FETCH', str(uid), f'(UID BODY.PEEK[]<0.{max_bytes + 1}>)')
                    literals = [p[1] for p in parts if isinstance(p, tuple)] if status == 'OK' else []
                    if len(literals) != 1 or not isinstance(literals[0], bytes):
                        raise error('Source fetch failed; capture rolled back.')
                    raw = literals[0]
                    if len(raw) != size:
                        raise error('Source size mismatch; capture rolled back.')
                parsed = parse_source(raw or b'')
                if raw is None:
                    parsed.update(capture_status='oversized', error_code='source_size_limit')
                result['inserted'] += store_email(db, target['id'], validity, uid, size, date, raw, parsed)
                _, _, seen_after = metadata(client, uid, error)
                result['examined'] += 1
                result['seen_unchanged'] += seen_before == seen_after
                result['unread_before'] += not seen_before
                result['unread_after'] += not seen_after
                if parsed['capture_status'] in ('parse_failed', 'oversized'):
                    result[parsed['capture_status']] += 1
            boundary = selected[-1] if len(uids) > limit else end
            db.execute("""UPDATE imap_receiver.mailboxes SET last_uid=%s,
                last_scan_at=now(), last_error_code=NULL WHERE id=%s""", (boundary, target['id']))
            result['more_pending'] = len(uids) > limit
    return result
