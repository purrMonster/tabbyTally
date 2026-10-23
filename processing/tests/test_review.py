import copy
import hashlib
import hmac
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import test_foundation as foundation
import test_extraction
from test_extraction import response
from tabby_processing import review, review_api, outbox, extraction


class CallbackTests(unittest.TestCase):
    def test_throttle_is_retryable_without_reapplying_decision(self):
        import http.client
        import threading
        from http.server import HTTPServer
        started=threading.Event(); stop=threading.Event(); servers=[]
        def server_factory(address, handler):
            server=HTTPServer(('127.0.0.1',0),handler)
            servers.append(server); started.set(); return server
        with tempfile.TemporaryDirectory() as root:
            key=Path(root)/'key'; key.write_bytes(b'x'*32)
            with patch.dict(os.environ,REVIEW_SIGNING_KEY_FILE=str(key),REVIEW_ALLOWED_ACTORS='owner'), \
                 patch.object(review_api,'HTTPServer',side_effect=server_factory), \
                 patch.object(review_api.time,'monotonic',return_value=100), \
                 patch.object(review_api,'connect'), \
                 patch.object(review_api.review,'decide',return_value={'ok':True}) as decide:
                thread=threading.Thread(target=review_api.serve,args=(stop,)); thread.start()
                try:
                    self.assertTrue(started.wait(5))
                    body=b'{}'; stamp=str(int(review_api.time.time()))
                    signature=hmac.new(b'x'*32,stamp.encode()+b'\nowner\n'+body,hashlib.sha256).hexdigest()
                    for expected in (200,429):
                        client=http.client.HTTPConnection('127.0.0.1',servers[0].server_port,timeout=5)
                        try:
                            client.request('POST','/review/actions',body,{'X-Review-Timestamp':stamp,'X-Review-Actor':'owner','X-Review-Signature':signature})
                            response=client.getresponse(); response.read()
                            self.assertEqual(response.status,expected)
                            if expected==429: self.assertEqual(response.getheader('Retry-After'),'1')
                        finally: client.close()
                    decide.assert_called_once()
                finally:
                    stop.set(); thread.join(5)
                    self.assertFalse(thread.is_alive())

    def test_authentication_actor_timestamp_and_signature(self):
        body=b'{}'; key=b'x'*32
        headers={'X-Review-Timestamp':'1000','X-Review-Actor':'owner'}
        headers['X-Review-Signature']=hmac.new(key,b'1000\nowner\n'+body,hashlib.sha256).hexdigest()
        self.assertEqual(review_api.authenticate(headers,body,key,1000),'owner')
        for data,now in [(b'{"forged":true}',1000),(body,1400)]:
            with self.assertRaises(ValueError): review_api.authenticate(headers,data,key,now)


@unittest.skipUnless(os.environ.get('RUN_PROCESSING_TESTS')=='1','isolated PostgreSQL required')
class ReviewTests(unittest.TestCase):
    setUp=foundation.FoundationTests.setUp
    cleanup=foundation.FoundationTests.cleanup
    email=foundation.FoundationTests.email
    prepare=test_extraction.ExtractionTests.prepare

    def pending(self):
        extraction.register_mapping(self.db,'Synthetic','INR','ExampleBank','card','1234','v1','test')
        job,config=self.prepare()
        extraction.process(self.db,job,config,extractor=lambda *a,**k:response())
        return self.db.execute('SELECT * FROM processing.reviews').fetchone()

    def request(self,r,action='approve'):
        return dict(action_id='unique-action',review_id=str(r['id']),revision=r['revision'],action=action,reason='Verified synthetic source')

    def test_repeat_conflicting_and_stale_actions(self):
        r=self.pending(); request=self.request(r)
        result=review.decide(self.db,'owner',request)
        self.assertEqual(result,review.decide(self.db,'owner',request))
        with self.assertRaises(ValueError): review.decide(self.db,'other',request)
        with self.assertRaises(ValueError): review.decide(self.db,'owner',dict(request,reason='different'))
        with self.assertRaises(ValueError): review.decide(self.db,'owner',dict(request,action_id='second'))
        self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.review_decisions').fetchone()['n'],1)

    def test_correction_revalidates_and_is_atomic(self):
        r=self.pending(); request=self.request(r,'correct'); request['facts']=response() and __import__('json').loads(response()['raw'])['events'][0]
        request['facts']['transaction_amount']['amount']='-1'
        with self.assertRaises(ValueError): review.decide(self.db,'owner',request)
        self.assertEqual(self.db.execute('SELECT revision FROM processing.reviews').fetchone()['revision'],1)
        self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.action_receipts').fetchone()['n'],0)

    def test_outbox_failure_retry_and_expired_claim(self):
        self.pending()
        def fail(*a,**k): raise RuntimeError('private failure')
        self.assertEqual(outbox.once(self.db,fail)['outcome'],'pending')
        self.db.execute("UPDATE processing.notification_outbox SET due_at=clock_timestamp()-interval '1 second'")
        self.assertEqual(outbox.once(self.db,lambda *a,**k:None)['outcome'],'sent')
        self.assertEqual(outbox.once(self.db,fail)['outcome'],'idle')

    def test_review_backup_restore(self):
        r=self.pending(); review.decide(self.db,'owner',self.request(r,'defer'))
        with tempfile.TemporaryDirectory() as root,patch.object(foundation.backup,'ROOT',Path(root)),patch.dict(os.environ,PGDATABASE=self.name):
            archive=foundation.backup.create_backup(include_processing=True)
            foundation.backup.verify_backup(archive)

    def test_outbox_stale_sender_cannot_overwrite(self):
        self.pending()
        def stale(*a,**k):
            self.db.execute("UPDATE processing.notification_outbox SET token=gen_random_uuid() WHERE state='leased'")
        self.assertEqual(outbox.once(self.db,stale)['outcome'],'lost_lease')
        self.assertEqual(self.db.execute('SELECT state FROM processing.notification_outbox').fetchone()['state'],'leased')
        self.db.execute("UPDATE processing.notification_outbox SET lease_expires_at=clock_timestamp()-interval '1 second'")
        self.assertEqual(outbox.once(self.db,lambda *a,**k:None)['outcome'],'sent')

    def test_source_review_correction(self):
        extraction.register_mapping(self.db,'Synthetic','INR','ExampleBank','card','1234','v1','test')
        job,config=self.prepare()
        extraction.process(self.db,job,config,extractor=lambda *a,**k:{'raw':'{}','metadata':{}})
        r=self.db.execute('SELECT * FROM processing.reviews').fetchone()
        request=self.request(r,'correct')
        request['facts']=__import__('json').loads(response()['raw'])['events'][0]
        review.decide(self.db,'owner',request)
        self.assertEqual(self.db.execute('SELECT disposition FROM processing.transaction_candidates').fetchone()['disposition'],'ready')

    def test_concurrent_actions_only_one_wins(self):
        import concurrent.futures
        r=self.pending()
        def decide(action_id):
            from tabby_processing.database import connect
            with connect(dbname=self.name) as db:
                try:
                    review.decide(db,'owner',dict(self.request(r,'ignore'),action_id=action_id))
                    return True
                except ValueError: return False
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(decide,['one','two'])),1)

    def test_decision_rolls_back_if_notification_insert_fails(self):
        r=self.pending()
        with patch.object(review,'enqueue',side_effect=RuntimeError('synthetic crash')):
            with self.assertRaises(RuntimeError): review.decide(self.db,'owner',self.request(r))
        self.assertEqual(self.db.execute('SELECT state,revision FROM processing.reviews').fetchone(),{'state':'open','revision':1})
        self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.review_decisions').fetchone()['n'],0)
        self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.action_receipts').fetchone()['n'],0)

    def test_outbox_exhaustion_is_inspectable(self):
        self.pending()
        def fail(*a,**k): raise RuntimeError('private details')
        for _ in range(5):
            self.db.execute("UPDATE processing.notification_outbox SET due_at=clock_timestamp()-interval '1 second'")
            result=outbox.once(self.db,fail)
        self.assertEqual(result['outcome'],'dead')
        self.assertEqual(self.db.execute('SELECT last_error FROM processing.notification_outbox').fetchone()['last_error'],'delivery_failed')
