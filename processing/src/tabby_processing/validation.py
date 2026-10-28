"""Conservative deterministic checks; unsupported bank formats remain review-only."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import copy

from .facts import evidence_spans
from . import templates, bank_dates

VERSION = 'financial-rules-v7'
APPROVED_PURCHASE_RULES = frozenset({'hdfc_card_v1','hdfc_rupay_upi_v1',
    'hdfc_without_otp_v1','hdfc_noticed_card_v1','hdfc_netbanking_v1','icici_card_v1'})
# Explicit supported units, not a claim of universal ISO currency coverage.
MINOR_UNITS = {'INR':2,'USD':2,'EUR':2,'GBP':2,'JPY':0,'KWD':3,'AED':2,'SGD':2,'AUD':2,'CAD':2}


def money(value, currency):
    if currency not in MINOR_UNITS:
        raise ValueError('unsupported_currency')
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,15}(?:\.\d{1,6})?',value):
        raise ValueError('invalid_amount')
    try:
        amount = Decimal(value)
        minor = amount * 10 ** MINOR_UNITS[currency]
        if amount<=0 or minor != minor.to_integral_value() or minor>9_000_000_000_000_000:
            raise ValueError('invalid_amount_precision_or_range')
        return int(minor)
    except InvalidOperation:
        raise ValueError('invalid_amount') from None


def validate(event, text, mappings, *, today=None, message_date=None):
    reasons = []
    spans, evidence_issues = evidence_spans(event,text)
    reasons.extend(evidence_issues)
    by_field = {s['field']:s['quote'] for s in spans}
    matched = templates.parse(text, message_date)
    supported = matched[0]['events'][0] if matched else None
    # Only exact, independently reparsed facts receive template normalization.
    template_verified = supported is not None and event == supported
    event=copy.deepcopy(event)
    fallbacks=[]
    approved_purchase=template_verified and matched[1] in APPROVED_PURCHASE_RULES
    budgeting_status=None
    if approved_purchase:
        # These known formats report a completed purchase, not an OTP request or
        # transfer initiation. Budget eligibility does not assert bank settlement.
        budgeting_status='confirmed_purchase_alert'
        event['unresolved_fields']=[f for f in event['unresolved_fields'] if f!='settlement_status']
    # Only a genuinely absent date gets the email date. A present but ambiguous
    # or conflicting date must not be silently replaced.
    undated_template = template_verified and not any(
        e['field']=='transaction_date' for e in supported['evidence']) and matched[1] in (
        'hdfc_repayment_v1','hdfc_netbanking_v1','hdfc_rtgs_initiated_v1')
    email_day=bank_dates.header_date(message_date)
    if event['transaction_date'] is None and undated_template and email_day:
        event['transaction_date']=email_day.isoformat()
        event['unresolved_fields']=[f for f in event['unresolved_fields'] if f!='transaction_date']
        fallbacks.append({'field':'transaction_date','rule':'email_date_fallback',
                          'value':event['transaction_date'],'source_message_date':str(message_date)})
    if (template_verified and event['account_identifier'] is None and
            event['product']=='account' and event['event_type']=='transfer' and event['direction']=='debit'):
        possible=[m for m in mappings if m['enabled'] and m['bank']==event['bank']
                  and m['product']=='account' and m.get('owned',True)
                  and m.get('account_status','active')=='active']
        unique={(str(m['account_id']),m['account_identifier']):m for m in possible}
        if len(unique)==1:
            inferred=next(iter(unique.values()))
            event['account_identifier']=inferred['account_identifier']
            event['unresolved_fields']=[f for f in event['unresolved_fields'] if f!='source_account']
            fallbacks.append({'field':'account_identifier','rule':'sole_owned_bank_account',
                              'value':event['account_identifier'],'bank':event['bank'],
                              'mapping_id':str(inferred['id']),'mapping_version':inferred['version']})
    fallback_fields={f['field'] for f in fallbacks}
    critical = ['event_type','bank','product','account_identifier','direction','transaction_date']
    for field in critical:
        if event[field] in (None,'','unknown'):
            reasons.append('missing_'+field)
        if field not in by_field and field not in fallback_fields:
            reasons.append('evidence_'+field)
    for field in ('bank','product','account_identifier','reference','merchant'):
        value = event[field]
        if value is not None and (field not in by_field or value.casefold() not in by_field[field].casefold()) and not (field=='product' and template_verified) and field not in fallback_fields:
            reasons.append('unsupported_'+field)
    parsed_money = {}
    for field in ('transaction_amount','original_amount','billed_amount'):
        pair = event[field]
        if pair['amount'] is None and pair['currency'] is None and field != 'transaction_amount':
            continue
        try:
            parsed_money[field] = money(pair['amount'],pair['currency'])
        except ValueError as error:
            reasons.append(str(error))
        quote = by_field.get(field,'')
        amount_pattern = r'(?<![\d.])' + re.escape(pair['amount'] or '') + r'(?![\d.])'
        if (not pair['amount'] or not re.search(amount_pattern,quote.replace(',','')) or not pair['currency'] or not re.search(r'\b'+re.escape(pair['currency'])+r'\b',quote)) and not (field=='transaction_amount' and template_verified and field in by_field):
            reasons.append('evidence_'+field)
        if re.search(r'\b(balance|available|outstanding|due|limit)\b',quote,re.I):
            reasons.append('amount_role_ambiguous')
    date_resolution = None
    if matched:
        supported = matched[0]['events'][0]
        if supported['transaction_date'] and all(event[key] == supported[key] for key in
                ('transaction_date','bank','product','transaction_amount')):
            date_resolution = {'rule_version':bank_dates.VERSION,'template_rule':matched[1],
                               'reference_date':str(bank_dates.header_date(message_date)) if bank_dates.header_date(message_date) else None,
                               'resolved_date':supported['transaction_date'],
                               'source_quote':next(e['quote'] for e in supported['evidence'] if e['field']=='transaction_date')}
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',event['transaction_date'] or ''):
            raise ValueError()
        parsed_date = date.fromisoformat(event['transaction_date'])
        if parsed_date > (today or date.today()):
            reasons.append('future_date')
        if event['transaction_date'] not in by_field.get('transaction_date','') and not date_resolution and 'transaction_date' not in fallback_fields:
            reasons.append('date_requires_format_rule')
    except ValueError:
        reasons.append('invalid_or_ambiguous_date')
    matches = [m for m in mappings if m['enabled'] and
               all(m[k] == event[k] for k in ('bank','product','account_identifier'))]
    account = matches[0] if len(matches)==1 else None
    if not account:
        reasons.append('account_unmatched' if not matches else 'account_ambiguous')
    if event['unresolved_fields']:
        reasons.append('unresolved_fields')
    if event['event_type'] in ('transfer','card_repayment'):
        reasons.append('counterpart_link_required')
    if event['event_type'] in ('unknown','authorization') or (event['lifecycle'] != 'posted' and not approved_purchase):
        reasons.append('unsupported_lifecycle')
    expected = 'credit' if event['event_type'] in ('income','refund') else 'debit'
    if template_verified and matched[1]=='axis_loan_credit_v1':
        expected='credit'  # Loan-account credit is still a repayment expense.
    if event['event_type'] not in ('transfer','card_repayment') and event['direction'] != expected:
        reasons.append('direction_mismatch')
    # Loan repayments use the expense interpretation in v1.
    treatment = 'movement' if event['event_type'] in ('transfer','card_repayment') else (
        'income' if event['event_type']=='income' else 'refund' if event['event_type']=='refund' else 'expense')
    if event['event_type']=='transfer':
        # Source direction alone cannot prove own-account movement. Outgoing
        # payments follow the user's expense policy pending counterpart review.
        treatment='expense' if event['direction']=='debit' else 'unresolved'
        reasons.append('counterparty_ownership_unresolved')
    selected = 'billed_amount' if 'billed_amount' in parsed_money else 'transaction_amount'
    if account and event[selected]['currency'] != account['currency']:
        reasons.append('account_currency_unresolved')
    # A foreign alert may populate transaction_amount only. Settlement is still
    # unknown; never require a duplicate original_amount to detect this case.
    foreign_purchase = account and any(
        event[field]['currency'] and event[field]['currency'] != account['currency']
        for field in ('transaction_amount', 'original_amount'))
    if foreign_purchase and ('billed_amount' not in parsed_money or
                             event['billed_amount']['currency'] != account['currency'] or
                             'evidence_billed_amount' in reasons or
                             'evidence_missing_or_ambiguous' in reasons):
        reasons.append('foreign_billing_unresolved')
    reconciliation = None
    if 'foreign_billing_unresolved' in reasons:
        # This is missing settlement evidence, not a retryable extraction failure.
        # Preserve source money, but expose no selected account-currency amount.
        selected = None
        reconciliation = {'status':'awaiting_statement_or_manual_correction',
                          'required_currency':account['currency'],
                          'resolution_sources':['statement_transaction','manual_correction']}
    # Corpus coverage exists, but readiness approval is separate from coverage.
    if not approved_purchase: reasons.append('format_not_regression_approved')
    return {'disposition':'needs_review' if reasons else 'ready','reasons':sorted(set(reasons)), 'evidence':spans,
            'account_id':str(account['account_id']) if account else None,
            'mapping_id':str(account['id']) if account else None,
            'mapping_version':account['version'] if account else None,
            'minor_units':parsed_money,'selected_amount':selected,'treatment':treatment,
            'budgeting_status':budgeting_status,'effective_facts':event,'fallbacks':fallbacks,
            'date_resolution':date_resolution,'reconciliation':reconciliation,'rule_version':VERSION}
