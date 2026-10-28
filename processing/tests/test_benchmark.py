"""Scoring rules must not quietly forgive malformed financial fields."""
import unittest
from score_benchmark import equivalent

class BenchmarkScoringTests(unittest.TestCase):
    def test_money_decimal_equivalence(self):
        self.assertTrue(equivalent('amount','12.50','12.5'))
        self.assertFalse(equivalent('amount','12.50','1250'))
        self.assertFalse(equivalent('amount','12.50',None))

    def test_account_mask_only(self):
        self.assertTrue(equivalent('account_identifier','1234','XX1234'))
        self.assertFalse(equivalent('account_identifier','1234','ending 1234'))
        self.assertFalse(equivalent('account_identifier','1234','XX5678'))

    def test_unknown_date_must_remain_unknown(self):
        self.assertTrue(equivalent('transaction_date',None,None))
        self.assertFalse(equivalent('transaction_date',None,'2026-09-22'))
