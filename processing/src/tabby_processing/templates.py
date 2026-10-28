"""Narrow, evidence-preserving alert parsers. Proposals only; no import approval."""
import re

from . import facts, bank_dates

VERSION='bank-templates-v5'
AMOUNT=r'(?P<amount>(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3}|[0-9]+)(?:\.[0-9]{1,3})?)'
CURRENCY=r'(?P<currency>Rs\.?|INR|USD|EUR|GBP)\s*'
RULES=[
    ('hdfc_nach_v1','Account update for your HDFC Bank A / c','HDFC Bank','account','transfer',
     re.compile(CURRENCY+AMOUNT+r' has been debited from HDFC Bank Account Number (?P<account>X+[0-9]{4}) towards (?P<merchant>[^\n]+?) with UMRN (?P<reference>[A-Z0-9]+) on (?P<date>[0-9]{2}-[A-Za-z]{3}-[0-9]{4})\.'),'%d-%b-%Y'),
    ('axis_loan_debit_v1','Debit transaction alert for Axis Bank A/c','Axis Bank','account','loan_payment',
     re.compile(r'your A/c no\. (?P<account>XX[0-9]{4}) has been debited with '+CURRENCY+AMOUNT+r' on (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{4}) [0-9:]+ IST by (?P<merchant>MB/Loan Closure/[A-Z0-9]+)\.'),'%d-%m-%Y'),
    ('axis_upi_credit_v1',re.compile(r'INR [0-9,.]+ was credited to your A/c\.'),'Axis Bank','account','transfer',
     re.compile(r'Amount Credited:\n'+CURRENCY+AMOUNT+r'\nAccount Number:\n(?P<account>XX[0-9]{4})\nDate & Time:\n(?P<date>[0-9]{2}-[0-9]{2}-[0-9]{2}), [0-9:]+ IST\nTransaction Info:\nUPI/P2A/(?P<reference>[0-9]+)/(?P<merchant>[^\n]+)'),'%d-%m-%y'),
    ('icici_repayment_v1','Payment received on your ICICI Bank Credit Card.','ICICI Bank','Credit Card','card_repayment',
     re.compile(r'We have received payment of '+CURRENCY+AMOUNT+r' on your ICICI Bank Credit Card account (?P<account>[0-9]{4} XXXX XXXX [0-9]{4}) on (?P<date>[0-9]{2}-[A-Za-z]{3}-[0-9]{4})\.'),'%d-%b-%Y'),
    ('hdfc_upi_credit_v1','View: Account update for your HDFC Bank A/c','HDFC Bank','account','transfer',
     re.compile(CURRENCY+AMOUNT+r' has been successfully credited to your HDFC Bank account ending in (?P<account>[0-9]{4})\.\nTransaction Details:\na\. Date: (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{2})\nb\. Sender: (?P<merchant>[^\n]+)\nc\. UPI Reference No\.: (?P<reference>[0-9]+)'),'%d-%m-%y'),
    ('hdfc_repayment_v1','View: Account update for your HDFC Bank A/c','HDFC Bank','account','card_repayment',
     re.compile(r'This is to inform you that an amount of '+CURRENCY+AMOUNT+r' has been debited from your Account number (?P<account>XX[0-9]{4}) for Credit Card Payment done using HDFC Bank Online Banking\.'),None),
    ('hdfc_netbanking_v1','View: Account update for your HDFC Bank A/c','HDFC Bank','account','purchase',
     re.compile(r'Thank you for using HDFC Bank NetBanking\.\nWe hope your payment experience was safe and smooth\.\nPayment Details\nAmount: '+CURRENCY+AMOUNT+r'\nFrom Account: (?P<account>\*+[0-9]{4})\nPaid To: (?P<merchant>[^\n]+)'),None),
    ('hdfc_rtgs_initiated_v1','View: Account update for your HDFC Bank A/c','HDFC Bank','account','authorization',
     re.compile(r'You have successfully initiated a RTGS transaction of '+CURRENCY+AMOUNT+r' from your HDFC Bank A/c (?P<account>XX[0-9]{4}) for a transfer to payee (?P<merchant>[^\n]+?) using HDFC Bank Online Banking\.'),None),
    ('hdfc_rtgs_completed_v1','View: Account update for your HDFC Bank A/c','HDFC Bank','account','transfer',
     re.compile(r'Your RTGS transfer has been completed successfully\.[^\n]*\nTransaction Details:\nAmount: '+CURRENCY+AMOUNT+r'\nCredited to beneficiary A/c ending: (?P<beneficiary>XX[0-9]{4})\nDate & Time: (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{4}) at [0-9:]+\nReference Number: (?P<reference>[A-Z0-9]+)'),'%d-%m-%Y'),
    ('hdfc_without_otp_v1','A charge just happened on your Credit Card without OTP','HDFC Bank','Card','purchase',
     re.compile(r'Thank you for using your HDFC Bank Card (?P<account>XX[0-9]{4}) for '+CURRENCY+AMOUNT+r' at (?P<merchant>[^\n]+?) on (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{4}) [0-9:]+\.'), '%d-%m-%Y'),
    ('hdfc_noticed_card_v1','We noticed a transaction on your Credit Card','HDFC Bank','Credit Card','purchase',
     re.compile(r'Thank you for using your HDFC Bank Credit Card ending in (?P<account>[0-9]{4})\.You made a transaction of '+CURRENCY+AMOUNT+r' at (?P<merchant>[^\n]+?) on (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{4}) [0-9:]+\.'), '%d-%m-%Y'),
    ('axis_loan_credit_v1',None,'Axis Bank','Loan account','loan_payment',
     re.compile(r'Payment of '+CURRENCY+AMOUNT+r' has been credited to your Loan account no\. (?P<account>XX[0-9]{4}) on (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{4})\.'), '%d-%m-%Y'),
    ('hdfc_rupay_upi_v1','You have done a UPI txn. Check details!', 'HDFC Bank','Credit Card','purchase',
     re.compile(r'^'+CURRENCY+AMOUNT+r' has been debited from your RuPay Credit Card \(ending (?P<account>[0-9]{4})\)\nPaid to (?P<merchant>[^\n]+)\nDate: (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{2})\nUPI Transaction Reference Number: (?P<reference>[0-9]+)(?:\.|$)',re.M),
     '%d-%m-%y'),
    ('hdfc_upi_v1','You have done a UPI txn. Check details!', 'HDFC Bank','account','transfer',
     re.compile(r'^'+CURRENCY+AMOUNT+r' is debited from your account ending (?P<account>[0-9]{4}) towards VPA (?P<merchant>[^\n]+) on (?P<date>[0-9]{2}-[0-9]{2}-[0-9]{2})\.\nUPI transaction reference no\.: (?P<reference>[0-9]+)\.',re.M),
     '%d-%m-%y'),
    ('hdfc_card_v1','A payment was made using your Credit Card','HDFC Bank','Credit Card','purchase',
     re.compile(r'^We would like to inform you that '+CURRENCY+AMOUNT+r' has been debited from your HDFC Bank Credit Card ending (?P<account>[0-9]{4}) towards (?P<merchant>[^\n]+?) on (?P<date>[0-9]{2} [A-Za-z]{3}, [0-9]{4}) at [0-9:]+\.',re.M),
     '%d %b, %Y'),
    ('icici_card_v1','Transaction alert for your ICICI Bank Credit Card','ICICI Bank','Credit Card','purchase',
     re.compile(r'^Your ICICI Bank Credit Card (?P<account>[Xx*]*[0-9]{4}) has been used for a transaction of '+CURRENCY+AMOUNT+r' on (?P<date>[A-Za-z]{3} [0-9]{2}, [0-9]{4}) at [0-9:]+\. Info: (?P<merchant>[^\n]+)\.',re.M),
     '%b %d, %Y'),
]


def parse(text, message_date=None):
    first,_,body=text.partition('\n\n')
    if not first.startswith('Subject: '): return None
    for name,subject,bank,product,kind,pattern,date_format in RULES:
        actual_subject=first.removeprefix('Subject: ').lstrip('❗ ').strip()
        if subject is None:
            if not re.fullmatch(r'Payment credited to your Loan account no\. XX[0-9]{4}',actual_subject): continue
        elif isinstance(subject,re.Pattern):
            if not subject.fullmatch(actual_subject): continue
        elif actual_subject!=subject: continue
        matches=list(pattern.finditer(body))
        if not matches: continue
        if len(matches)!=1: return None
        match=matches[0]; groups=match.groupdict()
        try:
            day=bank_dates.resolve(groups['date'],date_format,message_date) if date_format else None
        except ValueError:
            return None
        currency='INR' if groups['currency'].startswith('Rs') else groups['currency']
        clause=match.group(0)
        bank_quote=clause if bank in clause else None
        if bank_quote is None:
            position=body.find(bank)
            if position>=0:
                candidate=body[max(0,position-30):position+len(bank)+40]
                if body.count(candidate)==1: bank_quote=candidate
        if not bank_quote: return None
        # Refuse a second event-bearing clause outside the recognized one; mixed mail
        # needs full extraction rather than an incomplete single-event shortcut.
        remainder=body[:match.start()]+body[match.end():]
        if re.search(r'(?i)(?:\bdebited\b|\bcredited\b|has been used for a transaction|payment (?:received|of))',remainder): return None
        if re.search(r'(?i)\b(?:declined|reversed|unsuccessful|cancelled|pending)\b',body): return None
        event={key:None for key in ('bank','product','account_identifier','transaction_date','merchant','reference')}
        event.update(event_type=kind,bank=bank,product=product,account_identifier=groups['account'][-4:] if groups.get('account') else None,
                     transaction_amount={'amount':groups['amount'].replace(',',''),'currency':currency},
                     original_amount={'amount':None,'currency':None},billed_amount={'amount':None,'currency':None},
                     direction='credit' if name in ('axis_loan_credit_v1','axis_upi_credit_v1','hdfc_upi_credit_v1','icici_repayment_v1') else 'debit',transaction_date=day,merchant=groups.get('merchant'),reference=groups.get('reference'),
                     lifecycle='unknown',unresolved_fields=['settlement_status']+([] if day else ['transaction_date']),evidence=[])
        for field in ('event_type','product','account_identifier','transaction_amount','direction','merchant','transaction_date','reference'):
            if field in ('reference','merchant','transaction_date') and event[field] is None: continue
            event['evidence'].append({'field':field,'quote':clause})
        event['evidence'].append({'field':'bank','quote':bank_quote})
        if groups.get('beneficiary'):
            event['unresolved_fields'].extend(['source_account','beneficiary_ownership'])
            event['evidence'].append({'field':'beneficiary_account_identifier','quote':clause})
        value={'schema_version':facts.VERSION,'classification':'transaction','reason':name,'events':[event]}
        try:
            facts.check(value,facts.SCHEMA)
        except facts.InvalidOutput:
            return None
        return value,name
    return None
