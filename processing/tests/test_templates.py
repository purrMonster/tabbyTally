"""Anonymized format regressions; transaction-like negative content is deliberate."""
import unittest
from tabby_processing import normalize, templates


class TemplateTests(unittest.TestCase):
    def test_undated_payments_do_not_borrow_email_date(self):
        subject='View: Account update for your HDFC Bank A/c'
        for body,kind in [
            ('This is to inform you that an amount of Rs. 1,250.00 has been debited from your Account number XX1234 for Credit Card Payment done using HDFC Bank Online Banking.','card_repayment'),
            ('Thank you for using HDFC Bank NetBanking.\nWe hope your payment experience was safe and smooth.\nPayment Details\nAmount: Rs. 125.00\nFrom Account: **********1234\nPaid To: SHOP','purchase'),
            ('You have successfully initiated a RTGS transaction of Rs. 1,00,000.00 from your HDFC Bank A/c XX1234 for a transfer to payee SHOP using HDFC Bank Online Banking.','authorization')]:
            text=normalize.normalize(dict(capture_status='captured',subject=subject,text_body=body)).text
            event=templates.parse(text,'2026-10-17')[0]['events'][0]
            self.assertIsNone(event['transaction_date'])
            self.assertEqual(event['event_type'],kind)
            self.assertNotEqual(event['lifecycle'],'posted')

    def test_rtgs_beneficiary_is_not_source_account(self):
        body=('Greetings from HDFC Bank!\nYour RTGS transfer has been completed successfully.\n'
              'Transaction Details:\nAmount: INR 1,00,000.00\nCredited to beneficiary A/c ending: XX9876\n'
              'Date & Time: 17-10-2026 at 12:00:00\nReference Number: HDFCR123456')
        result=self.parse('View: Account update for your HDFC Bank A/c',body)
        event=result[0]['events'][0]
        self.assertIsNone(event['account_identifier'])
        self.assertIn('source_account',event['unresolved_fields'])
        self.assertIsNone(self.parse('View: Account update for your HDFC Bank A/c',body.replace('completed successfully','declined')))

    def test_loan_credit_is_not_income(self):
        result=self.parse('Payment credited to your Loan account no. XX1234',
            'Payment of INR 2500 has been credited to your Loan account no. XX1234 on 25-09-2026. Regards, Axis Bank Ltd.')
        event=result[0]['events'][0]
        self.assertEqual(event['event_type'],'loan_payment')
        self.assertEqual(event['direction'],'credit')
        self.assertEqual(event['transaction_date'],'2026-09-25')

    def test_without_otp_is_purchase_not_otp(self):
        body='Thank you for using your HDFC Bank Card XX1234 for Rs. 125.0 at SHOP on 02-10-2026 19:03:00. This transaction was conducted without OTP/PIN.'
        result=self.parse('A charge just happened on your Credit Card without OTP',body)
        self.assertEqual(result[0]['events'][0]['event_type'],'purchase')
        self.assertIsNone(self.parse('OTP For online Ecom Transaction',body))

    def test_rupay_upi_is_card_not_savings(self):
        body=('Greetings from HDFC Bank!\nRs.125.00 has been debited from your RuPay Credit Card (ending 1234)\n'
              'Paid to shop@bank\nDate: 22-09-26\nUPI Transaction Reference Number: 123456789012\nImportant Note:')
        result=self.parse('You have done a UPI txn. Check details!',body)
        self.assertEqual(result[1],'hdfc_rupay_upi_v1')
        event=result[0]['events'][0]
        self.assertEqual(event['product'],'Credit Card')
        self.assertEqual(event['transaction_amount']['amount'],'125.00')
        self.assertIsNone(event['transaction_date'])
        self.assertIsNone(self.parse('You have done a UPI txn. Check details!',body.replace('has been debited','may be debited')))

    def parse(self, subject, body):
        return templates.parse(normalize.normalize(dict(subject=subject,text_body=body,capture_status='captured')).text)

    def test_purchase_amount_not_available_limit(self):
        result=self.parse('Transaction alert for your ICICI Bank Credit Card',
            'Your ICICI Bank Credit Card XX1234 has been used for a transaction of INR 125.00 on Sep 22, 2026 at 20:12:00. Info: UPI-999-Shop.\nThe Available Credit Limit is INR 100000.00. Never share your OTP.')
        event=result[0]['events'][0]
        self.assertEqual(event['transaction_amount'],dict(amount='125.00',currency='INR'))
        self.assertEqual(event['transaction_date'],'2026-09-22')
        self.assertEqual(event['lifecycle'],'unknown')

    def test_upi_date_century_stays_unknown(self):
        result=self.parse('You have done a UPI txn. Check details!',
            'Greetings from HDFC Bank!\nRs.125.00 is debited from your account ending 1234 towards VPA shop@bank (Shop) on 22-09-26.\nUPI transaction reference no.: 123456789012.')
        self.assertIsNone(result[0]['events'][0]['transaction_date'])

    def test_negative_bodies_even_with_transaction_subject(self):
        for subject in (r[1] for r in templates.RULES):
            if not isinstance(subject,str): continue
            for body in ('123456 is the OTP for the transaction of USD 1.00 using card 1234.',
                         'Convert your outstanding balance of INR 50000.00 to SmartEMI.',
                         'Total payment due INR 5000.00. Pay before 22-09-2026.',
                         'Your biometric authentication has been enabled.',
                         'Standing instruction set: account to be debited INR 500.00.',
                         'Your attempted transaction of INR 125.00 was declined.'):
                with self.subTest(subject=subject,body=body):
                    self.assertIsNone(self.parse(subject,body))

    def test_multiple_events_refuse_shortcut(self):
        clause='We would like to inform you that Rs. 125.00 has been debited from your HDFC Bank Credit Card ending 1234 towards Shop on 23 Sep, 2026 at 11:21:00.'
        self.assertIsNone(self.parse('A payment was made using your Credit Card',clause+'\n'+clause))

    def test_html_markup_and_visible_limits_are_separate(self):
        source=dict(capture_status='captured',html_body='<div title="'+'x'*30000+'">Notice</div>')
        self.assertEqual(normalize.normalize(source).issues,())
        source['html_body']='<div>'+'x'*24001+'</div>'
        self.assertIn('input_incomplete',normalize.normalize(source).issues)
        source['html_body']='<div title="'+'x'*1000001+'">Notice</div>'
        self.assertIn('input_incomplete',normalize.normalize(source).issues)
