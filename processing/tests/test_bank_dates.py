import unittest
from tabby_processing import bank_dates, templates, normalize, validation


class BankDateTests(unittest.TestCase):
    def test_boundaries_and_invalid_context(self):
        for raw, header, expected in [
            ('31-12-26','2027-01-01','2026-12-31'),
            ('01-01-27','2026-12-31','2027-01-01'),
            ('01-02-26','2026-02-02','2026-02-01'),
            ('31-12-99','2100-01-01','2099-12-31'),
            ('29-02-24','2024-03-01','2024-02-29'),
            ('01-01-26','2026-03-01',None),
            ('01-01-26','bad',None),
            ('01-01-26',None,None),
        ]:
            with self.subTest(raw=raw, header=header):
                self.assertEqual(bank_dates.resolve(raw,'%d-%m-%y',header),expected)
        for raw in ('31-04-26','29-02-25','00-01-26'):
            with self.assertRaises(ValueError): bank_dates.resolve(raw,'%d-%m-%y','2026-04-30')

    def test_template_date_evidence_is_revalidated(self):
        text=normalize.normalize(dict(capture_status='captured',
            subject='You have done a UPI txn. Check details!',
            text_body='Greetings from HDFC Bank!\nRs.125.00 is debited from your account ending 1234 towards VPA shop@bank (Shop) on 01-02-26.\nUPI transaction reference no.: 123456789012.')).text
        value=templates.parse(text,'2026-02-01')[0]['events'][0]
        self.assertEqual(value['transaction_date'],'2026-02-01')
        result=validation.validate(value,text,[],message_date='2026-02-01')
        self.assertNotIn('date_requires_format_rule',result['reasons'])
        self.assertEqual(result['date_resolution']['reference_date'],'2026-02-01')
        self.assertIn('date_requires_format_rule',validation.validate(value,text,[])['reasons'])
        value['transaction_date']='2026-01-02'
        self.assertIn('date_requires_format_rule',validation.validate(value,text,[],message_date='2026-02-01')['reasons'])
