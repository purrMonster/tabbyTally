"""Opt-in client for the proposed meowGram durable-send-v1 contract.

This contract is not yet implemented by the inspected meowGram branch.
The subprocess bounds the entire request, including DNS and slow responses.
"""
import base64
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from uuid import UUID

CONTRACT = 'durable-send-v1'


def config():
    if os.environ.get('MEOWGRAM_VERIFIED_CONTRACT') != CONTRACT:
        raise ValueError('Verify provider contract before enabling delivery')
    url = urlsplit(os.environ.get('MEOWGRAM_SEND_URL', ''))
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or not url.path or url.path == '/'):
        raise ValueError('Explicit HTTPS send endpoint required')
    username = Path(os.environ['MEOWGRAM_USERNAME_FILE']).read_text(encoding='utf-8').strip()
    password = Path(os.environ['MEOWGRAM_PASSWORD_FILE']).read_text(encoding='utf-8').rstrip('\r\n')
    if not username or ':' in username or not password or any(c in username + password for c in '\r\n'):
        raise ValueError('Invalid local credentials')
    return url, username, password


def message(payload):
    # Whitelist fields: never forward email text or arbitrary outbox payload fields.
    review_id = str(UUID(payload['review_id']))
    revision = payload['revision']
    if type(revision) is not int or revision < 1 or payload['state'] not in ('open', 'resolved'):
        raise ValueError('Invalid notification')
    return {'text_content': f"tabbyTally review {review_id}\nRevision {revision}: {payload['state']}\n"
            'Inspect this review in the private processing console.'}


def deliver(payload, delivery_id):
    url, username, password = config()
    key = str(UUID(delivery_id))
    body = json.dumps(message(payload)).encode('utf-8')
    auth = base64.b64encode(f'{username}:{password}'.encode()).decode('ascii')
    connection = http.client.HTTPSConnection(url.hostname, url.port, timeout=15)
    try:
        connection.request('POST', url.path, body, {'Authorization': 'Basic ' + auth,
                           'Content-Type': 'application/json', 'Idempotency-Key': key})
        response = connection.getresponse()
        # No redirects, no accepted/queued acknowledgments: only durable receipts.
        if response.status not in (200, 201):
            raise ValueError('Delivery not acknowledged')
        raw = response.read(16385)
        if len(raw) > 16384:
            raise ValueError('Oversized receipt')
        receipt = json.loads(raw)
        if (not isinstance(receipt, dict) or receipt.get('idempotency_key') != key
                or receipt.get('persisted') is not True
                or not isinstance(receipt.get('id'), str) or not receipt['id'].strip()):
            raise ValueError('Invalid durable receipt')
    finally:
        connection.close()


def send(payload, delivery_id, timeout=20):
    subprocess.run([sys.executable, '-m', 'tabby_processing.meowgram'],
                   input=json.dumps({'payload': payload, 'id': delivery_id}).encode(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=timeout, check=True)


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.buffer.read(65537))
        deliver(request['payload'], request['id'])
    except Exception:
        # Never print credentials, provider response, or message content.
        raise SystemExit(1)
