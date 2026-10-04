import unittest
from decimal import Decimal as D

from spend import digest, journal


def entry(day, amount, category, note="x", currency="AMD", src="cli"):
    return journal.Entry(day, note, category, D(amount), currency, f"src:{src}", 0, 0)


AUG = [entry("2026-08-10", "100000", "home", "rent")]
SEP = [entry("2026-09-02", "88000", "travel", "visa concord charters 2", src="bank"),
       entry("2026-09-05", "4500", "groceries", "sas supermarket"),
       entry("2026-09-05", "1500", "eating-out", "coffee"),
       entry("2026-09-07", "9000", "other", "61 terminal pos 3"),
       entry("2026-09-26", "92.97", "subscriptions", "anthropic claude sub anthropic", "USD", "bank")]


class Pretty(unittest.TestCase):
    def test_pretty(self):
        self.assertEqual(digest.pretty("visa concord charters 2"), "Concord Charters")
        self.assertEqual(digest.pretty("google google one support.googl"), "Google One Support.googl")
        self.assertEqual(digest.pretty("avag arzumanyan ie yerevan am 2"), "Avag Arzumanyan Ie")
        self.assertEqual(digest.pretty("mne 95023610moneynet_s seriate"), "Mne Moneynet_s Seriate")
        self.assertEqual(digest.pretty("գանձում 1 sms-ի համար"), "գանձում 1 sms-ի համար")


class Subcategories(unittest.TestCase):
    def test_breakdown_line_under_a_category(self):
        es = [entry("2026-10-01", "1500", "transport:taxi"), entry("2026-10-02", "300", "transport:public"),
              entry("2026-10-03", "900", "groceries")]
        d = digest.Digest.build("2026-10", es)
        self.assertEqual(d.categories("AMD"), [("transport", D("1800")), ("groceries", D("900"))])
        self.assertEqual(d.subcategories("AMD", "transport"), [("taxi", D("1500")), ("public", D("300"))])
        self.assertEqual(d.subcategories("AMD", "groceries"), [])
        self.assertIn("taxi 1,500 · public 300", digest.render_html(d))


class Summary(unittest.TestCase):
    def setUp(self):
        self.d = digest.Digest.build("2026-09", AUG + SEP)

    def test_numbers(self):
        self.assertEqual(self.d.curs, ["AMD", "USD"])
        self.assertEqual(self.d.total("AMD"), D("103000"))
        self.assertEqual(self.d.days(), {2: D("88000"), 5: D("6000"), 7: D("9000")})
        self.assertEqual(self.d.delta(), "3% more than August (+3,000 AMD)")

    def test_highlights(self):
        hs = self.d.highlights()
        self.assertEqual(hs[0], "Most went to **travel**: 88,000 AMD, 85% of everything in AMD.")
        self.assertIn("Biggest single payment: **88,000 AMD**, Concord Charters (travel, Sep 2).", hs)
        self.assertIn("Biggest day: **Wednesday, Sep 2**, 88,000 AMD.", hs)
        self.assertIn("Subscriptions: **92.97 USD** (Anthropic).", hs)
        self.assertIn("**1 payment** (9,000 AMD) still uncategorized: fix with `spend fix`.", hs)
        self.assertEqual(hs[-1], "That's 3% more than August (+3,000 AMD).")

    def test_html(self):
        html = digest.render_html(self.d)
        for part in ("103,000", "+ 92.97 USD", "Highlights", "<b ", "Where it went", "Spent in USD",
                     "Day by day", 'title="Sep 2: 88,000 AMD"', "Biggest payments", "Concord Charters",
                     "Last 6 months", "prefers-color-scheme: dark"):
            self.assertIn(part, html)
        self.assertNotIn("**", html)
        self.assertNotIn("<script", html)

    def test_text(self):
        text = digest.render_text(self.d)
        self.assertTrue(text.startswith("Spending · September 2026: 103,000 AMD + 92.97 USD"))
        self.assertIn("• Most went to travel: 88,000 AMD", text)
        self.assertIn("Last 6 months", text)  # August + September have data


if __name__ == "__main__":
    unittest.main()
