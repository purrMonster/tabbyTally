import copy
import unittest
from tabby_processing import accounts, correlation


def register():
    return {'accounts':[dict(bank='Example',account_type='credit_card',last_four=s,
        label='Primary' if i==0 else 'Other',currency='INR',owned=True,status='active',
        billing_group='cards',billing_group_primary=i==0) for i,s in enumerate(('0012','1234','5678'))]}


class AccountTests(unittest.TestCase):
    def test_shared_billing_preserves_card_suffixes(self):
        rows=accounts.compile_register(register())
        self.assertEqual(len({r['account_id'] for r in rows}),1)
        self.assertEqual({r['account_identifier'] for r in rows},{'0012','1234','5678'})
        self.assertEqual(rows,accounts.compile_register(register()))
        self.assertEqual({r['label'] for r in rows},{'Primary'})

    def test_invalid_register_is_rejected(self):
        for key,value in [('currency',None),('owned',False),('last_four','12'),('billing_group_primary',False)]:
            r=register(); r['accounts'][0][key]=value
            with self.assertRaises(ValueError): accounts.compile_register(r)

    def test_amount_alone_does_not_link(self):
        e=dict(transaction_amount={'amount':'125.00','currency':'INR'},transaction_date='2026-01-01',
               reference=None,direction='debit',event_type='transfer')
        other=copy.deepcopy(e); other['direction']='credit'
        rows=[dict(id='b',account_id='two',facts=other)]
        self.assertEqual(correlation.suggest(e,'one',rows),[])
        e['reference']=other['reference']='REF'
        result=correlation.suggest(e,'one',rows)
        self.assertEqual(result[0]['relationship'],'possible_own_transfer')
        self.assertTrue(result[0]['requires_review'])
        other['transaction_amount']['currency']='USD'
        self.assertEqual(correlation.suggest(e,'one',rows),[])
