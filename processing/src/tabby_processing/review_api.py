"""Loopback callback service. Deploy behind HTTPS; credentials stay in local files."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from .database import connect
from . import review


def authenticate(headers, body, key, now=None):
    stamp=headers.get('X-Review-Timestamp','')
    actor=headers.get('X-Review-Actor','')
    if not actor or len(actor)>100: raise ValueError('Unauthorized')
    if abs((now if now is not None else time.time())-int(stamp))>300: raise ValueError('Expired')
    signed=stamp.encode()+b'\n'+actor.encode()+b'\n'+body
    expected=hmac.new(key,signed,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,headers.get('X-Review-Signature','')): raise ValueError('Unauthorized')
    return actor


def serve(stop=None):
    key=Path(os.environ['REVIEW_SIGNING_KEY_FILE']).read_bytes().strip()
    allowed=set(os.environ['REVIEW_ALLOWED_ACTORS'].split(','))
    if len(key)<32 or not all(allowed): raise ValueError('Strong key and explicit actors required')
    last={}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def setup(self):
            super().setup(); self.connection.settimeout(10)
        def do_POST(self):
            try:
                if self.path!='/review/actions' or self.headers.get('Transfer-Encoding'): raise ValueError()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536: raise ValueError()
                body=self.rfile.read(size)
                actor=authenticate(self.headers,body,key)
                if actor not in allowed: raise ValueError()
                now=time.monotonic()
                if now-last.get(actor,0)<0.1:
                    self.send_response(429)
                    self.send_header('Retry-After','1')
                    self.send_header('Content-Length','0')
                    self.end_headers()
                    return
                last[actor]=now
            except (ValueError,TimeoutError):
                self.send_error(403); return
            try:
                with connect() as db: result=review.decide(db,actor,json.loads(body))
                data=json.dumps(result).encode(); self.send_response(200)
            except (ValueError,TypeError,KeyError):
                data=b'{"error":"invalid_or_stale_action"}'; self.send_response(409)
            except Exception:
                data=b'{"error":"temporarily_unavailable"}'; self.send_response(503)
            self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)
    with HTTPServer((os.environ.get('REVIEW_BIND','127.0.0.1'),int(os.environ.get('REVIEW_PORT','8091'))),Handler) as server:
        server.timeout=0.5
        while stop is None or not stop.is_set(): server.handle_request()
