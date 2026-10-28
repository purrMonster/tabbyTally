import copy
import unittest
from tabby_processing import normalize,templates,validation


class ReadinessTests(unittest.TestCase):
    def test_ready_purchase_and_false_ready_guards(self):
        text=normalize.normalize(dict(capture_status='captured',subject='A payment was made using your Credit Card',
            text_body='We would like to inform you that Rs. 125.00 has been debited from your HDFC Bank Credit Card ending 1234 towards Shop on 23 Sep, 2026 at 11:21:00.')).text
        event=templates.parse(text)[0]['events'][0]
        mapping=dict(id='m',account_id='a',version='v',enabled=True,bank='HDFC Bank',product='Credit Card',account_identifier='1234',currency='INR')
        self.assertEqual(validation.validate(event,text,[mapping])['disposition'],'ready')
        self.assertEqual(validation.validate(event,text,[])['disposition'],'needs_review')
        self.assertEqual(validation.validate(event,text,[mapping,mapping])['disposition'],'needs_review')
        for field,value in [('direction','credit'),('transaction_date','2026-01-01'),('account_identifier','5678')]:
            changed=copy.deepcopy(event); changed[field]=value
            self.assertNotEqual(validation.validate(changed,text,[mapping])['disposition'],'ready')
        changed=copy.deepcopy(event); changed['transaction_amount']['amount']='0'
        self.assertNotEqual(validation.validate(changed,text,[mapping])['disposition'],'ready')
        foreign=text.replace('Rs. 125.00','USD 125.00')
        e=templates.parse(foreign)[0]['events'][0]
        self.assertIn('foreign_billing_unresolved',validation.validate(e,foreign,[mapping])['reasons'])
        self.assertIsNone(templates.parse(text.replace('125.00','1,,25.00')))
        for contradiction in ('Transaction declined','Transaction pending','Payment reversed'):
            self.assertIsNone(templates.parse(text+'\n'+contradiction))
