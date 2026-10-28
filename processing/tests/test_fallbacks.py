import copy
import unittest
from tabby_processing import normalize, templates, validation


class FallbackTests(unittest.TestCase):
    def check(self, body, mappings=(), header='2026-10-17'):
        text=normalize.normalize(dict(capture_status='captured',subject='View: Account update for your HDFC Bank A/c',text_body=body)).text
        value=templates.parse(text,header)[0]['events'][0]
        original=copy.deepcopy(value)
        result=validation.validate(value,text,mappings,message_date=header)
        self.assertEqual(value,original)
        return result

    def test_email_date_fallback(self):
        body='This is to inform you that an amount of Rs. 125.00 has been debited from your Account number XX1234 for Credit Card Payment done using HDFC Bank Online Banking.'
        result=self.check(body)
        self.assertEqual(result['effective_facts']['transaction_date'],'2026-10-17')
        self.assertEqual(result['fallbacks'][0]['rule'],'email_date_fallback')
        self.assertNotIn('missing_transaction_date',result['reasons'])
        self.assertNotIn('evidence_transaction_date',result['reasons'])
        self.assertIsNone(self.check(body,header='bad')['effective_facts']['transaction_date'])

    def test_sole_source_account_and_ambiguity(self):
        body='Greetings from HDFC Bank!\nYour RTGS transfer has been completed successfully.\nTransaction Details:\nAmount: INR 125.00\nCredited to beneficiary A/c ending: XX9876\nDate & Time: 17-10-2026 at 12:00:00\nReference Number: HDFCR12345'
        mapping=dict(id='m',account_id='a',enabled=True,bank='HDFC Bank',product='account',account_identifier='1234',version='v',currency='INR')
        result=self.check(body,[mapping])
        self.assertEqual(result['effective_facts']['account_identifier'],'1234')
        self.assertEqual(result['account_id'],'a')
        self.assertNotIn('unsupported_account_identifier',result['reasons'])
        self.assertNotIn('account_unmatched',result['reasons'])
        for other in (dict(mapping,product='Credit Card'),dict(mapping,bank='Axis Bank'),dict(mapping,enabled=False)):
            self.assertIsNone(self.check(body,[other])['effective_facts']['account_identifier'])
        self.assertIsNone(self.check(body,[mapping,dict(mapping,id='n',account_id='b',account_identifier='5678')])['effective_facts']['account_identifier'])
