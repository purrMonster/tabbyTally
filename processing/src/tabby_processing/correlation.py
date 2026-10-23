"""Conservative relationship suggestions. Never merge or delete source events."""


def suggest(event, account_id, candidates):
    result=[]
    if not account_id: return result
    for row in candidates:
        other=row['facts']; other_account=row.get('account_id')
        if not other_account: continue
        amount=event['transaction_amount']; theirs=other['transaction_amount']
        from decimal import Decimal, InvalidOperation
        try:
            same_money=(amount['currency']==theirs['currency'] and amount['currency'] is not None
                        and Decimal(amount['amount'])==Decimal(theirs['amount']))
        except (InvalidOperation,TypeError):
            same_money=False
        same_date=bool(event['transaction_date'] and event['transaction_date']==other['transaction_date'])
        same_ref=bool(event['reference'] and event['reference']==other['reference'])
        if not same_money: continue
        opposite={event['direction'],other['direction']}=={'debit','credit'}
        kind=None
        if str(account_id)==str(other_account) and same_ref and event['direction']==other['direction']:
            kind='possible_duplicate'
        elif str(account_id)!=str(other_account) and opposite and same_date:
            if same_ref and event['event_type']==other['event_type']=='transfer':
                kind='possible_own_transfer'
            elif event['event_type']==other['event_type']=='card_repayment':
                kind='possible_card_repayment_pair'
            elif event['event_type']==other['event_type']=='loan_payment':
                kind='possible_loan_payment_pair'
        if kind:
            result.append({'candidate_id':str(row['id']),'relationship':kind,
                           'requires_review':True,'same_reference':same_ref})
    return result
