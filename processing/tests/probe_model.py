"""Explicit live smoke test: synthetic text only; no database, profile writes or secrets printed.

Run with model environment configured and processing/src on PYTHONPATH.
This is not part of unittest discovery and never runs automatically.
"""
import json
from tabby_processing import facts, model

CASES = [
    ('purchase','ExampleBank: Your card ending 1234 was debited INR 125.50 on 2026-01-02 for a completed purchase at Shop. Reference REF123. Available balance INR 5000.00.',
     'transaction','125.50','INR'),
    ('foreign','ExampleBank: Completed purchase of USD 12.50 on card ending 1234 at Shop on 2026-01-02. Reference FX123. Final INR billing amount is not yet available.',
     'transaction','12.50','USD'),
    ('reminder','ExampleBank reminder: Your card ending 1234 has a payment due of INR 2500.00 on 2026-01-20. This is a reminder only; no payment has been made.',
     'non_transaction',None,None),
]


def main():
    settings=model.config()
    listing=model.call(action='models',timeout=30)
    if not listing['selected_available']:
        raise model.ModelError('model_alias_unavailable')
    failed=False
    for name,text,classification,amount,currency in CASES:
        try:
            result=model.call(text,timeout=1200)
        except model.ModelError as error:
            print(json.dumps({'case':name,'passed':False,'code':error.code,'metadata':error.metadata}),flush=True)
            failed=True
            continue
        try:
            value=facts.parse(result['raw'])
        except facts.InvalidOutput as error:
            try:
                decoded=json.loads(result['raw'])
                summary={'classification':decoded.get('classification'),'event_count':len(decoded.get('events',[]))}
            except (ValueError,TypeError,AttributeError):
                summary={}
            print(json.dumps({'case':name,'schema_valid':False,'code':str(error),
                              'summary':summary,'metadata':result['metadata']}),flush=True)
            failed=True
            continue
        valid=value['classification']==classification
        if amount:
            valid=valid and len(value['events'])==1
            if value['events']:
                event=value['events'][0]
                valid=valid and event['transaction_amount']=={'amount':amount,'currency':currency}
                valid=valid and event['account_identifier']=='1234'
                valid=valid and event['transaction_date']=='2026-01-02'
                if name=='foreign':
                    # The source explicitly names INR as billing currency. Keeping that
                    # known currency is valid; inventing a numeric final charge is not.
                    valid=valid and event['billed_amount']['amount'] is None and event['billed_amount']['currency'] in (None,'INR')
        failed=failed or not valid
        print(json.dumps({'case':name,'schema_valid':True,'expected_fields_match':valid,
                          'classification':value['classification'],
                          'proposed_amounts':[e['transaction_amount'] for e in value['events']],
                          'checked_fields':[{'account_identifier':e['account_identifier'],
                                             'transaction_date':e['transaction_date'],
                                             'billed_amount':e['billed_amount']} for e in value['events']],
                          'metadata':result['metadata']}),flush=True)
    return int(failed)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (model.ModelError,facts.InvalidOutput) as error:
        print(json.dumps({'probe_failed':type(error).__name__,'code':str(error)}))
        raise SystemExit(1)
