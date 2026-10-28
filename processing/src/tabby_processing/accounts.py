"""Compile explicit owner confirmations; never infer ownership from a payee name."""
import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid5


PRODUCTS = {'bank_account':('account',), 'credit_card':('Credit Card','Card'),
            'loan':('Loan account',)}


def compile_register(register):
    rows=register['accounts']; result=[]; seen=set(); groups={}
    version='confirmed-'+hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()[:16]
    for row in rows:
        key=(row['bank'],row['account_type'],row['last_four'])
        if key in seen or not re.fullmatch(r'[0-9]{4}',row['last_four']):
            raise ValueError('Duplicate or invalid account identifier')
        seen.add(key)
        if row['owned'] is not True or row['currency'] != 'INR':
            raise ValueError('This register requires confirmed owned INR accounts')
        if row['status'] not in ('active','closed') or row['account_type'] not in PRODUCTS:
            raise ValueError('Invalid account type or status')
        group=row.get('billing_group')
        if group:
            if row['account_type']!='credit_card': raise ValueError('Only cards share billing groups')
            groups.setdefault(group,[]).append(row)
    for members in groups.values():
        if len({r['bank'] for r in members})!=1 or sum(r.get('billing_group_primary',False) for r in members)!=1:
            raise ValueError('Billing group requires one bank and one primary')
    for row in rows:
        group=row.get('billing_group')
        identity=[row['bank'],'billing_group',group] if group else [row['bank'],row['account_type'],row['last_four']]
        account_id=str(uuid5(NAMESPACE_URL,'tabbytally/account/'+json.dumps(identity)))
        primary=next(r for r in groups[group] if r.get('billing_group_primary')) if group else row
        for product in PRODUCTS[row['account_type']]:
            result.append(dict(id=str(uuid5(NAMESPACE_URL,account_id+product+row['last_four']+version)),
                account_id=account_id,label=primary['label'],currency=row['currency'],bank=row['bank'],
                product=product,account_identifier=row['last_four'],version=version,enabled=True,
                owned=True,account_type=row['account_type'],account_status=row['status']))
    return result


def install(db, register, reason):
    from .discovery import audit
    mappings=compile_register(register)
    with db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('processing.account-register',0))")
        for m in mappings:
            existing=db.execute('SELECT * FROM processing.logical_accounts WHERE id=%s',(m['account_id'],)).fetchone()
            if existing and (existing['currency']!=m['currency'] or existing['label']!=m['label']):
                raise ValueError('Existing account differs; explicit migration required')
            db.execute('INSERT INTO processing.logical_accounts(id,label,currency) VALUES (%s,%s,%s) ON CONFLICT(id) DO NOTHING',
                       (m['account_id'],m['label'],m['currency']))
            other=db.execute('SELECT id FROM processing.account_mappings WHERE enabled AND bank=%s AND product=%s AND account_identifier=%s AND id<>%s',
                             (m['bank'],m['product'],m['account_identifier'],m['id'])).fetchone()
            if other: raise ValueError('Existing mapping conflicts; explicit migration required')
            db.execute('INSERT INTO processing.account_mappings(id,account_id,bank,product,account_identifier,version) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',
                       tuple(m[k] for k in ('id','account_id','bank','product','account_identifier','version')))
        audit(db,'install_account_register',None,reason)
    return {'logical_accounts':len({m['account_id'] for m in mappings}),'mappings':len(mappings)}
