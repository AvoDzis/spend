import unittest
from datetime import date
from decimal import Decimal

from spend.parse import ParseError, parse_many, parse_one

TODAY = date(2026, 10, 4)


class ParseOne(unittest.TestCase):
    def check(self, text, amount, currency, note, when=TODAY):
        e = parse_one(text, TODAY)
        self.assertEqual((e.amount, e.currency, e.note, e.date), (Decimal(amount), currency, note, when))

    def test_attached_currency(self):
        self.check("800dram supermarket", "800", "AMD", "supermarket")
        self.check("50usd jeans", "50", "USD", "jeans")
        self.check("20eur museum", "20", "EUR", "museum")

    def test_separate_currency(self):
        self.check("800 dram supermarket", "800", "AMD", "supermarket")
        self.check("usd 50 jeans", "50", "USD", "jeans")

    def test_symbols(self):
        self.check("$12.50 lunch", "12.50", "USD", "lunch")
        self.check("12€ lunch", "12", "EUR", "lunch")
        self.check("3000֏ taxi", "3000", "AMD", "taxi")

    def test_default_amd_and_amount_anywhere(self):
        self.check("taxi 1200", "1200", "AMD", "taxi")
        self.check("1200 yandex taxi", "1200", "AMD", "yandex taxi")

    def test_thousands_and_k(self):
        self.check("1,500 coffee", "1500", "AMD", "coffee")
        self.check("1.5k coffee", "1500.0", "AMD", "coffee")
        self.check("250k rent", "250000", "AMD", "rent")

    def test_words_that_look_numeric_stay_in_note(self):
        self.check("2kg apples 900", "900", "AMD", "2kg apples")

    def test_dates(self):
        self.check("yesterday 1200 taxi", "1200", "AMD", "taxi", date(2026, 10, 3))
        self.check("2026-09-30 5000 gym", "5000", "AMD", "gym", date(2026, 9, 30))

    def test_short_dates(self):
        self.check("oct 1 1200 taxi", "1200", "AMD", "taxi", date(2026, 10, 1))
        self.check("1 oct 1200 taxi", "1200", "AMD", "taxi", date(2026, 10, 1))
        self.check("Oct 3: 800 bus", "800", "AMD", "bus", date(2026, 10, 3))
        self.check("2nd october 300 coffee", "300", "AMD", "coffee", date(2026, 10, 2))
        self.check("sep30 5000 gym", "5000", "AMD", "gym", date(2026, 9, 30))
        self.check("1200 taxi oct 1", "1200", "AMD", "taxi", date(2026, 10, 1))
        self.check("dec 30 5000 gift", "5000", "AMD", "gift", date(2025, 12, 30))  # most recent Dec 30
        self.check("oct 800 taxi", "800", "AMD", "oct taxi")  # no day: just a word

    def test_errors(self):
        with self.assertRaises(ParseError):
            parse_one("supermarket", TODAY)
        with self.assertRaises(ParseError):
            parse_one("800dram", TODAY)


class ParseMany(unittest.TestCase):
    def test_comma_list(self):
        es = parse_many("800dram supermarket, 50usd jeans", TODAY)
        self.assertEqual([(e.note, e.currency) for e in es], [("supermarket", "AMD"), ("jeans", "USD")])

    def test_chunk_without_amount_joins_previous(self):
        es = parse_many("4500 supermarket, milk and bread", TODAY)
        self.assertEqual(len(es), 1)
        self.assertEqual(es[0].note, "supermarket, milk and bread")

    def test_date_carries_on(self):
        es = parse_many("oct 1 1200 taxi, 4500 sas, oct 2 3000 coffee; 800 bus, oct 3 900 lunch", TODAY)
        self.assertEqual([(e.date.day, e.note) for e in es],
                         [(1, "taxi"), (1, "sas"), (2, "coffee"), (2, "bus"), (3, "lunch")])
        self.assertEqual([e.date for e in parse_many("300 coffee, yesterday 800 bus, 500 snack", TODAY)],
                         [TODAY, date(2026, 10, 3), date(2026, 10, 3)])

    def test_thousands_comma_not_split(self):
        self.assertEqual(len(parse_many("1,500 coffee; 800 bus", TODAY)), 2)


if __name__ == "__main__":
    unittest.main()
