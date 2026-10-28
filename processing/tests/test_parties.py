import unittest
from tabby_processing.parties import describe


class PartyTests(unittest.TestCase):
    def test_outgoing_payee_and_incoming_sender(self):
        event=dict(bank='Example Bank',product='account',account_identifier='1234',merchant='Shop / VPA',direction='debit')
        self.assertEqual(describe(event)['recipient'],'Shop / VPA')
        event['direction']='credit'
        self.assertEqual(describe(event)['sender'],'Shop / VPA')
        self.assertEqual(describe(event)['recipient'],'Example Bank account 1234')

    def test_beneficiary_suffix_does_not_become_source(self):
        event=dict(bank='Example Bank',product='account',account_identifier='1234',merchant=None,direction='debit',
                   evidence=[{'field':'beneficiary_account_identifier','quote':'Credited to beneficiary A/c ending: XX9876'}])
        self.assertEqual(describe(event)['recipient'],'Beneficiary account XX9876')
        self.assertEqual(describe(event)['sender'],'Example Bank account 1234')
        event['evidence']=[]
        self.assertIsNone(describe(event)['recipient'])
        self.assertIsNone(describe(None)['recipient'])
