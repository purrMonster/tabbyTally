"""Disposable cross-project test fixture; never included in production image."""
import json
import os
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from test_review import ReviewTests
from tabby_processing import review_api
from tabby_processing.database import connect

if os.environ.get('RUN_PROCESSING_TESTS') != '1' or os.environ.get('PGDATABASE') != 'processing_test':
    raise SystemExit('Disposable test database opt-in required')

case = ReviewTests('test_repeat_conflicting_and_stale_actions')
case.setUp()
row = case.pending()
os.environ['PGDATABASE'] = case.name
key = Path('/tmp/bridge-test-key')
key.write_bytes(b'k' * 32)
os.environ.update(REVIEW_SIGNING_KEY_FILE=str(key), REVIEW_ALLOWED_ACTORS='owner',
                  REVIEW_BIND='0.0.0.0', REVIEW_PORT='8091')
threading.Thread(target=review_api.serve, daemon=True).start()


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        with connect() as db:
            decisions = db.execute('SELECT count(*) AS n FROM processing.review_decisions').fetchone()['n']
            current = db.execute('SELECT revision,state FROM processing.reviews WHERE id=%s', (row['id'],)).fetchone()
        data = json.dumps(dict(review_id=str(row['id']), revision=current['revision'],
                               state=current['state'], decisions=decisions)).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


HTTPServer(('0.0.0.0', 8092), Fixture).serve_forever()
