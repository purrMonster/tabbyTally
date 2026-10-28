"""Synthetic extraction acceptance tests; no external model or real banking data."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_foundation as foundation
from tabby_processing import extraction, facts, jobs, model, normalize, validation, discovery, worker, templates


TEXT = 'ExampleBank card 1234 purchase debit INR 125.50 on 2026-01-02 merchant Shop reference REF123 posted'


def event():
    values = dict(event_type='purchase',bank='ExampleBank',product='card',account_identifier='1234',
                  direction='debit',transaction_date='2026-01-02',merchant='Shop',reference='REF123',lifecycle='posted')
    values.update(transaction_amount={'amount':'125.50','currency':'INR'},
                  original_amount={'amount':None,'currency':None},billed_amount={'amount':None,'currency':None},
                  unresolved_fields=[])
    values['evidence'] = [{'field':key,'quote':value} for key,value in values.items() if isinstance(value,str)]
    values['evidence'].append({'field':'transaction_amount','quote':'INR 125.50'})
    return values


def response(value=None):
    return {'raw':json.dumps({'schema_version':facts.VERSION,'classification':'transaction',
                             'reason':'synthetic fixture','events':[value or event()]}),
            'metadata':{'profile':'synthetic','prompt_version':model.PROMPT_VERSION}}


class ValidationTests(unittest.TestCase):
    def test_normalization_and_bounds(self):
        result = normalize.normalize({'capture_status':'captured','html_body':'<p>INR 125.50</p><script>bad</script><img src="https://invalid/">'})
        self.assertEqual(result.text,'INR 125.50')
        self.assertEqual(result.sha256,hashlib.sha256(result.text.encode()).hexdigest())
        self.assertEqual(normalize.normalize({'capture_status':'captured','text_body':'x'*24001}).issues,('input_incomplete',))
        self.assertIn('capture_incomplete',normalize.normalize({'capture_status':'oversized'}).issues)

    def test_strict_output_contract(self):
        self.assertEqual(facts.parse(response()['raw'])['events'][0],event())
        for raw in ('{}','{"x":1,"x":2}','NaN','[]','```json\n{}\n```',response()['raw'].replace('Shop','\\ud800')):
            with self.subTest(raw=raw[:20]), self.assertRaises(facts.InvalidOutput): facts.parse(raw)
        value = json.loads(response()['raw'])
        value['classification']='non_transaction'
        with self.assertRaises(facts.InvalidOutput): facts.parse(json.dumps(value))

    def test_currency_precision(self):
        for amount,currency,expected in [('125.50','INR',12550),('125','JPY',125),('1.234','KWD',1234)]:
            self.assertEqual(validation.money(amount,currency),expected)
        for amount,currency in [('0','INR'),('-1','INR'),('1.001','INR'),('1.2','JPY'),('NaN','INR'),('1e2','INR'),('1','XXX')]:
            with self.subTest(amount=amount,currency=currency),self.assertRaises(ValueError): validation.money(amount,currency)

    def test_amount_evidence_requires_whole_number(self):
        value=event()
        value['transaction_amount']['amount']='25.50'
        result=validation.validate(value,TEXT,[])
        self.assertIn('evidence_transaction_amount',result['reasons'])

    def test_balances_missing_accounts_and_lifecycle(self):
        value=event()
        value['evidence'][-1]['quote']='balance INR 125.50'
        value['lifecycle']='unknown'
        result=validation.validate(value,TEXT.replace('INR 125.50','balance INR 125.50'),[])
        for reason in ('amount_role_ambiguous','account_unmatched','unsupported_lifecycle','format_not_regression_approved'):
            self.assertIn(reason,result['reasons'])
        self.assertEqual(result['disposition'],'needs_review')

    def test_foreign_amount_never_invents_inr(self):
        value=event()
        value['transaction_amount']['currency']='USD'
        value['original_amount']=copy.deepcopy(value['transaction_amount'])
        mapping=dict(account_id='a',id='m',version='v',enabled=True,bank='ExampleBank',product='card',account_identifier='1234',currency='INR')
        result=validation.validate(value,TEXT,[mapping])
        self.assertIn('foreign_billing_unresolved',result['reasons'])
        self.assertNotIn('billed_amount',result['minor_units'])
        self.assertIn('account_ambiguous',validation.validate(value,TEXT,[mapping,mapping])['reasons'])

    def test_foreign_transaction_requires_evidenced_inr_settlement(self):
        value=event()
        value['transaction_amount']['currency']='USD'
        value['evidence'][-1]['quote']='USD 125.50'
        text=TEXT.replace('INR 125.50','USD 125.50')
        mapping=dict(account_id='a',id='m',version='v',enabled=True,bank='ExampleBank',product='card',account_identifier='1234',currency='INR')
        before=copy.deepcopy(value)
        result=validation.validate(value,text,[mapping])
        self.assertIn('foreign_billing_unresolved',result['reasons'])
        self.assertEqual(value,before)
        self.assertNotIn('billed_amount',result['minor_units'])
        self.assertIsNone(result['selected_amount'])
        self.assertEqual(result['reconciliation'],{
            'status':'awaiting_statement_or_manual_correction',
            'required_currency':'INR',
            'resolution_sources':['statement_transaction','manual_correction']})
        # A guessed INR amount cannot resolve the missing statement evidence.
        value['billed_amount']={'amount':'10400.00','currency':'INR'}
        self.assertIn('foreign_billing_unresolved',validation.validate(value,text,[mapping])['reasons'])
        value['evidence'].append({'field':'billed_amount','quote':'INR 10400.00'})
        result=validation.validate(value,text+' billed INR 10400.00',[mapping])
        self.assertNotIn('foreign_billing_unresolved',result['reasons'])
        self.assertEqual(result['selected_amount'],'billed_amount')
        self.assertIsNone(result['reconciliation'])
        self.assertEqual(result['minor_units']['billed_amount'],1040000)
        self.assertEqual(result['disposition'],'needs_review')
        # A second foreign amount is not INR settlement either.
        value['billed_amount']['currency']='USD'
        self.assertIn('foreign_billing_unresolved',validation.validate(value,text,[mapping])['reasons'])

    def test_movements_and_loan_treatment(self):
        for kind in ('transfer','card_repayment','loan_payment'):
            value=event(); value['event_type']=kind
            result=validation.validate(value,TEXT,[])
            self.assertEqual(result['treatment'],'movement' if kind=='card_repayment' else 'expense')
            if kind!='loan_payment': self.assertIn('counterpart_link_required',result['reasons'])

    def test_dates_and_ambiguous_evidence(self):
        value=event(); value['transaction_date']='01/02/26'
        self.assertIn('invalid_or_ambiguous_date',validation.validate(value,TEXT,[])['reasons'])
        self.assertIn('evidence_missing_or_ambiguous',validation.validate(event(),TEXT+' '+TEXT,[])['reasons'])


@unittest.skipUnless(os.environ.get('RUN_PROCESSING_TESTS')=='1','isolated PostgreSQL opt-in required')
class ExtractionTests(unittest.TestCase):
    setUp=foundation.FoundationTests.setUp
    cleanup=foundation.FoundationTests.cleanup
    email=foundation.FoundationTests.email
    expire=foundation.FoundationTests.expire
    due=foundation.FoundationTests.due

    def test_confirmed_register_is_idempotent_and_rejects_drift(self):
        from tabby_processing import accounts
        from test_accounts import register
        first=accounts.install(self.db,register(),'synthetic confirmation')
        self.assertEqual(first,accounts.install(self.db,register(),'repeat'))
        self.assertEqual(first,{'logical_accounts':1,'mappings':6})
        changed=register(); changed['accounts'][0]['label']='Changed'
        with self.assertRaises(ValueError): accounts.install(self.db,changed,'conflict')
        self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.account_mappings').fetchone()['n'],6)

    def prepare(self,uid=1,text=TEXT):
        email=self.email(uid)
        self.db.execute("UPDATE imap_receiver.emails SET capture_status='captured',text_body=%s,raw_email=%s,raw_sha256=%s WHERE id=%s",
                        (text,text.encode(),hashlib.sha256(text.encode()).hexdigest(),email))
        config=dict(model_identity='synthetic',profile='synthetic',schema_version=facts.VERSION,
                    rule_version=validation.VERSION,normalizer_version=normalize.VERSION,template_version=templates.VERSION)
        discovery.activate(self.db,'extract-test',email_ids=[email],config=config,mode='extract')
        discovery.reconcile(self.db)
        return jobs.claim(self.db),config

    def test_atomic_persistence_duplicates_and_source_immutability(self):
        extraction.register_mapping(self.db,'test','INR','ExampleBank','card','1234','v1','test')
        for uid in (1,2):
            job,config=self.prepare(uid)
            before=self.db.execute('SELECT * FROM imap_receiver.emails WHERE id=%s',(job['email_id'],)).fetchone()
            extraction.process(self.db,job,config,extractor=lambda *a,**k:response())
            self.assertEqual(before,self.db.execute('SELECT * FROM imap_receiver.emails WHERE id=%s',(job['email_id'],)).fetchone())
        rows=self.db.execute('SELECT * FROM processing.transaction_candidates ORDER BY created_at').fetchall()
        self.assertEqual([r['disposition'] for r in rows],['needs_review','duplicate_suspected'])
        self.assertEqual(rows[1]['duplicate_of'],rows[0]['id'])
        self.assertEqual(discovery.reconcile(self.db)['inserted'],0)

    def test_invalid_model_output_is_durable_review(self):
        job,config=self.prepare()
        result=extraction.process(self.db,job,config,extractor=lambda *a,**k:{'raw':'{bad','metadata':{}})
        self.assertEqual(result['outcome'],'review_required')
        row=self.db.execute('SELECT * FROM processing.extraction_results').fetchone()
        self.assertEqual(row['raw_output'],'{bad')
        self.assertIn('invalid_model_output',row['reasons'])

    def test_stale_extraction_cannot_save(self):
        job,config=self.prepare()
        self.expire(job['id']); jobs.recover(self.db); self.due()
        newer=jobs.claim(self.db)
        with self.assertRaises(jobs.LostLease): extraction.process(self.db,job,config,extractor=lambda *a,**k:response())
        self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.extraction_results').fetchone()['n'],0)
        extraction.process(self.db,newer,config,extractor=lambda *a,**k:response())

    def test_save_failure_rolls_back_everything(self):
        job,config=self.prepare()
        with patch.object(jobs,'complete',side_effect=RuntimeError('synthetic crash')):
            with self.assertRaises(RuntimeError): extraction.process(self.db,job,config,extractor=lambda *a,**k:response())
        for table in ('extraction_results','transaction_candidates','job_results'):
            self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.'+table).fetchone()['n'],0)

    def test_worker_outage_retries(self):
        job,config=self.prepare()
        self.expire(job['id']); jobs.recover(self.db); self.due()
        with patch.object(extraction,'pipeline_config',return_value=config),patch.object(model,'call',side_effect=model.ModelError('model_connection_failure',True)):
            result=worker.once(self.db)
        self.assertEqual(result['outcome'],'retry_wait')
        self.assertEqual(self.db.execute('SELECT last_error FROM processing.email_jobs').fetchone()['last_error'],'model_connection_failure')
        self.assertEqual(self.db.execute('SELECT count(*) n FROM processing.extraction_results').fetchone()['n'],0)

    def test_otp_and_model_only_ignore(self):
        job,config=self.prepare(text='Your OTP is 123456. It expires in 10 minutes.')
        with patch.object(model,'call',side_effect=AssertionError('must not call')):
            self.assertEqual(extraction.process(self.db,job,config,extractor=model.call)['outcome'],'ignored')
        job,config=self.prepare(2)
        raw=json.dumps(dict(schema_version=facts.VERSION,classification='non_transaction',reason='promotion',events=[]))
        self.assertEqual(extraction.process(self.db,job,config,extractor=lambda *a,**k:dict(raw=raw,metadata={}))['outcome'],'review_required')

    def test_backup_with_extraction_state(self):
        job,config=self.prepare()
        extraction.process(self.db,job,config,extractor=lambda *a,**k:response())
        backup=foundation.backup
        with tempfile.TemporaryDirectory() as root,patch.object(backup,'ROOT',Path(root)),patch.dict(os.environ,PGDATABASE=self.name):
            archive=backup.create_backup(include_processing=True)
            backup.verify_backup(archive)

    def test_extractor_permissions(self):
        from psycopg import errors
        job,config=self.prepare()
        foundation.admin.provision(self.db)
        self.db.execute('CREATE ROLE synthetic_worker NOLOGIN')
        self.addCleanup(lambda:self.admin.execute('DROP ROLE synthetic_worker'))
        self.db.execute('GRANT processing_runtime,processing_extractor TO synthetic_worker')
        with foundation.connect(dbname=self.name) as db:
            db.execute('SET ROLE synthetic_worker')
            extraction.process(db,job,config,extractor=lambda *a,**k:response())
            for query in ('SELECT raw_email FROM imap_receiver.emails','SELECT credential_ref FROM imap_receiver.accounts','UPDATE imap_receiver.emails SET subject=NULL'):
                with self.assertRaises(errors.InsufficientPrivilege): db.execute(query)
