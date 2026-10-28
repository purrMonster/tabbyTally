"""Direction-aware presentation of existing source facts; no model-output rewriting."""
import re


def describe(event):
    if not event:
        return {'recipient':None,'sender':None,'recipient_basis':'no_financial_event'}
    own=' '.join(str(event[k]) for k in ('bank','product','account_identifier') if event.get(k)) or None
    counterparty=event.get('merchant')
    if event.get('direction')=='credit':
        return {'recipient':own,'sender':counterparty,
                'recipient_basis':'credited_account','sender_basis':'merchant_counterparty_field'}
    if event.get('direction')!='debit':
        return {'recipient':None,'sender':None,'recipient_basis':'direction_unknown',
                'counterparty':counterparty}
    if counterparty:
        return {'recipient':counterparty,'sender':own,'recipient_basis':'merchant_counterparty_field'}
    # Completion alerts sometimes name only the beneficiary suffix. Preserve
    # that identifier rather than silently replacing it with the source account.
    for entry in event.get('evidence',[]):
        if entry['field']=='beneficiary_account_identifier':
            match=re.search(r'Credited to beneficiary A/c ending: (XX[0-9]{4})',entry['quote'])
            if match:
                return {'recipient':'Beneficiary account '+match[1],'sender':own,
                        'recipient_basis':'beneficiary_identifier_only'}
    return {'recipient':None,'sender':own,'recipient_basis':'not_identified_in_source'}
