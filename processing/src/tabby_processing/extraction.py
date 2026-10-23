"""Model extraction behind the existing job fence; no financial writes."""
import hashlib
import json
import re
import time

from psycopg.types.json import Jsonb

from . import facts, jobs, model, normalize, validation, templates, review


def pipeline_config():
    settings = model.config()
    return {'model_identity':settings['identity'],'profile':settings['profile'],
            'schema_version':facts.VERSION,'rule_version':validation.VERSION,
            'normalizer_version':normalize.VERSION,'template_version':templates.VERSION}


def _identity(event, checked):
    if not checked['account_id'] or not event['reference']:
        return None
    # An exact scoped reference is still only a duplicate suspicion until formats are approved.
    key = [checked['account_id'],event['reference'],event['event_type'],event['direction']]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()


def _ignored(text):
    # Whole-input rule only. A keyword cannot discard a mixed message/transaction.
    return bool(re.fullmatch(r'Your OTP is [0-9]{4,8}\. It expires in [0-9]{1,2} minutes\.',text))


def process(db, job, config, deadline=120, extractor=None):
    started = time.monotonic()
    # Production config must match before sending any source text. Tests inject a local extractor.
    if extractor is None:
        if pipeline_config() != config:
            raise model.ModelError('pipeline_model_configuration_changed')
        extractor = model.call
    source = db.execute("""SELECT capture_status,raw_sha256,subject,text_body,html_body,message_date
        FROM imap_receiver.emails WHERE id=%s""",(job['email_id'],)).fetchone()
    normalized = normalize.normalize(source)
    reasons = list(normalized.issues)
    parsed, raw, metadata, candidates = None, None, {}, []
    kind = 'review_required'
    if not reasons and _ignored(normalized.text):
        kind, reasons = 'ignored', ['whole_message_otp_v1']
    elif not reasons:
        try:
            matched=templates.parse(normalized.text,source.get('message_date'))
            response = ({'raw':json.dumps(matched[0]),'metadata':{'processor':'deterministic_template',
                         'template_version':templates.VERSION,'template_rule':matched[1]}}
                        if matched else extractor(normalized.text,timeout=max(0,deadline-(time.monotonic()-started)-5)))
            raw, metadata = response['raw'], response['metadata']
            parsed = facts.parse(raw)
        except facts.InvalidOutput:
            reasons.append('invalid_model_output')
        except model.ModelError as error:
            metadata = error.metadata
            if error.transient:
                raise
            if error.code in ('model_input_budget','model_output_incomplete','model_response_limit','model_response_invalid'):
                reasons.append(error.code)
            else:
                raise
        if parsed:
            if parsed['classification'] == 'transaction':
                mappings = db.execute("""SELECT m.*,a.currency FROM processing.account_mappings m
                    JOIN processing.logical_accounts a ON a.id=m.account_id WHERE m.enabled""").fetchall()
                for event in parsed['events']:
                    checked = validation.validate(event,normalized.text,mappings,
                                                  message_date=source.get('message_date'))
                    candidates.append((checked['effective_facts'],checked))
                kind = 'extracted'
            else:
                # Model-only classification cannot silently discard banking source evidence.
                reasons.append('classification_requires_review')
    if time.monotonic()-started >= deadline:
        raise model.ModelError('model_deadline',True)
    with db.transaction():
        jobs.owned(db,job['id'],job['lease_token'])
        extraction_id = db.execute("""INSERT INTO processing.extraction_results
            (job_id,attempt_id,source_sha256,input_sha256,normalizer_version,normalized_text,
             schema_version,rule_version,model_metadata,raw_output,facts,reasons)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (job['id'],job['attempt_id'],source['raw_sha256'],normalized.sha256,normalized.version,
             normalized.text,facts.VERSION,validation.VERSION,Jsonb(metadata),raw,
             Jsonb(parsed) if parsed else None,Jsonb(reasons))).fetchone()['id']
        # Serialize by scoped event identity across different source emails/pipeline versions.
        keys = sorted(set(key for event,checked in candidates if (key:=_identity(event,checked))))
        for key in keys:
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(key,))
        for index,(event,checked) in enumerate(candidates):
            key = _identity(event,checked)
            duplicate = None
            if key:
                duplicate = db.execute('SELECT id FROM processing.transaction_candidates WHERE identity_key=%s ORDER BY created_at,id LIMIT 1',(key,)).fetchone()
            if duplicate:
                checked['disposition'] = 'duplicate_suspected'
                checked['reasons'].append('shared_account_reference')
            db.execute("""INSERT INTO processing.transaction_candidates
                (extraction_id,event_index,facts,validation,disposition,account_id,identity_key,duplicate_of)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",(extraction_id,index,Jsonb(event),Jsonb(checked),
                checked['disposition'],checked['account_id'],key,duplicate['id'] if duplicate else None))
        if kind!='ignored': review.ensure(db,extraction_id)
        jobs.complete(db,job['id'],job['lease_token'],kind,
                      {'extraction_id':str(extraction_id),'candidate_count':len(candidates),'reasons':reasons})
    return {'extraction_id':str(extraction_id),'candidate_count':len(candidates),'outcome':kind}


def register_mapping(db, label, currency, bank, product, identifier, version, reason):
    from .discovery import audit
    if currency not in validation.MINOR_UNITS or not re.fullmatch(r'[xX*.-]*[0-9]{4}',identifier):
        raise ValueError('Supported currency and masked/suffix-only identifier required')
    if any(not isinstance(s,str) or not s or len(s)>80 for s in (label,bank,product,version)):
        raise ValueError('Bounded nonempty mapping fields required')
    with db.transaction():
        account = db.execute('INSERT INTO processing.logical_accounts(label,currency) VALUES (%s,%s) RETURNING id',(label,currency)).fetchone()['id']
        mapping = db.execute("""INSERT INTO processing.account_mappings(account_id,bank,product,account_identifier,version)
            VALUES (%s,%s,%s,%s,%s) RETURNING id""",(account,bank,product,identifier,version)).fetchone()['id']
        audit(db,'register_mapping',mapping,reason)
        return {'account_id':str(account),'mapping_id':str(mapping)}
