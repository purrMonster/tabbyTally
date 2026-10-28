"""Audited, revision-fenced review decisions shared by CLI and authenticated API."""
import hashlib
import json
import re
from datetime import date
from psycopg.types.json import Jsonb
from . import facts, validation


def enqueue(db, review):
    payload={'review_id':str(review['id']),'revision':review['revision'],
             'state':review['state'],'message':'Email processing review updated'}
    db.execute('INSERT INTO processing.notification_outbox(review_id,revision,payload) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
               (review['id'],review['revision'],Jsonb(payload)))


def ensure(db, extraction_id):
    candidates=db.execute('SELECT id,disposition FROM processing.transaction_candidates WHERE extraction_id=%s',(extraction_id,)).fetchall()
    targets=[c['id'] for c in candidates if c['disposition']!='ready'] if candidates else [None]
    for target in targets:
        row=db.execute('INSERT INTO processing.reviews(extraction_id,candidate_id) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING *',
                       (extraction_id,target)).fetchone()
        if row: enqueue(db,row)


def decide(db, actor, request):
    if not isinstance(actor,str) or not 1<=len(actor)<=100: raise ValueError('Invalid actor')
    if set(request)-{'action_id','review_id','revision','action','facts','reason','treatment'}: raise ValueError('Unexpected fields')
    if not isinstance(request.get('action_id'),str) or not 1<=len(request['action_id'])<=120: raise ValueError('Invalid action ID')
    if not isinstance(request.get('reason'),str) or not 1<=len(request['reason'])<=500: raise ValueError('Reason required')
    action=request.get('action')
    if action not in ('approve','correct','ignore','defer'): raise ValueError('Invalid action')
    if action in ('ignore','defer') and ('facts' in request or 'treatment' in request): raise ValueError('Unexpected correction')
    if type(request.get('revision')) is not int: raise ValueError('Revision required')
    digest=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
    with db.transaction():
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(request['action_id'],))
        receipt=db.execute('SELECT * FROM processing.action_receipts WHERE id=%s',(request['action_id'],)).fetchone()
        if receipt:
            if receipt['actor']!=actor or receipt['digest']!=digest: raise ValueError('Action replay conflict')
            return receipt['result']
        row=db.execute('SELECT * FROM processing.reviews WHERE id=%s FOR UPDATE',(request['review_id'],)).fetchone()
        if not row or row['state']!='open' or row['revision']!=request['revision']: raise ValueError('Stale review')
        candidate=db.execute('SELECT * FROM processing.transaction_candidates WHERE id=%s FOR UPDATE',(row['candidate_id'],)).fetchone() if row['candidate_id'] else None
        before=candidate['facts'] if candidate else None
        after=request.get('facts',before)
        if action in ('approve','correct'):
            if not candidate and action!='correct': raise ValueError('Source-only review requires corrected facts')
            if action=='approve' and 'facts' in request: raise ValueError('Use correct to change facts')
            if action=='correct' and 'facts' not in request: raise ValueError('Correct requires full facts')
            facts.check(after,facts.SCHEMA['properties']['events']['items'])
            mappings=db.execute('SELECT m.*,a.currency FROM processing.account_mappings m JOIN processing.logical_accounts a ON a.id=m.account_id WHERE enabled').fetchall()
            extraction=db.execute('SELECT normalized_text FROM processing.extraction_results WHERE id=%s',(row['extraction_id'],)).fetchone()
            checked=validation.validate(after,extraction['normalized_text'],mappings)
            for field in ('transaction_amount','original_amount','billed_amount'):
                pair=after[field]
                if pair['amount'] is not None: validation.money(pair['amount'],pair['currency'])
            # Explicit human attestation can supply evidence/lifecycle decisions,
            # but never bypass structural money, date or account constraints.
            if not checked['account_id']: raise ValueError('Resolve account mapping first')
            selected='billed_amount' if after['billed_amount']['amount'] is not None else 'transaction_amount'
            minor=validation.money(**dict(value=after[selected]['amount'],currency=after[selected]['currency']))
            account=next(m for m in mappings if str(m['id'])==checked['mapping_id'])
            if after[selected]['currency']!=account['currency']: raise ValueError('Final account currency amount required')
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',after['transaction_date'] or '') or date.fromisoformat(after['transaction_date'])>date.today(): raise ValueError('Valid nonfuture date required')
            if after['lifecycle']!='posted' or after['direction'] not in ('debit','credit') or after['event_type'] in ('authorization','unknown') or after['unresolved_fields']:
                raise ValueError('Resolve lifecycle/direction/unknown fields first')
            treatment=request.get('treatment',checked['treatment'])
            if treatment not in ('expense','income','refund','movement'): raise ValueError('Treatment required')
            if after['event_type'] in ('transfer','card_repayment') and 'treatment' not in request: raise ValueError('Explicit counterpart treatment required')
            if candidate and candidate['duplicate_of']: raise ValueError('Duplicate must remain ignored or be investigated; cannot approve twice')
            from .extraction import _identity
            identity=_identity(after,checked)
            if identity:
                db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(identity,))
                duplicate=db.execute("SELECT id FROM processing.transaction_candidates WHERE identity_key=%s AND disposition<>'ignored' AND (%s::uuid IS NULL OR id<>%s::uuid) LIMIT 1",
                    (identity,candidate['id'] if candidate else None,candidate['id'] if candidate else None)).fetchone()
                if duplicate: raise ValueError('Duplicate reference requires investigation')
            if not candidate:
                candidate=db.execute("INSERT INTO processing.transaction_candidates(extraction_id,event_index,facts,validation,disposition) VALUES (%s,0,%s,%s,'needs_review') RETURNING *",
                                     (row['extraction_id'],Jsonb(after),Jsonb(checked))).fetchone()
                db.execute('UPDATE processing.reviews SET candidate_id=%s WHERE id=%s',(candidate['id'],row['id']))
            checked.update(disposition='ready',reasons=[],treatment=treatment,selected_amount=selected,
                           human_attestation={'actor':actor,'action_id':request['action_id'],'reason':request['reason']})
            checked['minor_units'][selected]=minor
            db.execute('UPDATE processing.transaction_candidates SET facts=%s,validation=%s,account_id=%s,identity_key=%s,disposition=\'ready\',revision=revision+1 WHERE id=%s',
                       (Jsonb(after),Jsonb(checked),checked['account_id'],identity,candidate['id']))
        elif action=='ignore' and candidate:
            db.execute("UPDATE processing.transaction_candidates SET disposition='ignored',revision=revision+1 WHERE id=%s",(candidate['id'],))
        db.execute('INSERT INTO processing.review_decisions(review_id,actor,action,previous_revision,before_facts,after_facts,reason) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                   (row['id'],actor,action,row['revision'],Jsonb(before),Jsonb(after),request['reason']))
        updated=db.execute('UPDATE processing.reviews SET revision=revision+1,state=%s WHERE id=%s RETURNING *',
                           ('open' if action=='defer' else 'resolved',row['id'])).fetchone()
        enqueue(db,updated)
        result={'review_id':str(row['id']),'revision':updated['revision'],'state':updated['state'],'action':action}
        db.execute('INSERT INTO processing.action_receipts(id,actor,digest,result) VALUES (%s,%s,%s,%s)',
                   (request['action_id'],actor,digest,Jsonb(result)))
        return result
