"""The month-end digest behind `spend report`: one summary of a month, rendered as plain text
(terminal, email fallback) and as an email-safe HTML page (tables + inline styles, no scripts).

Layout, top to bottom: the total as one big number, three small figures, a few plain-language
highlights, bars per category, a calendar shaded by daily spending, the biggest expenses, and a
monthly trend once there are at least two months of data. Charts use one blue hue: bars in a single
step, the calendar light → dark by amount. Text stays in neutral inks, never in the chart color.
"""
import calendar
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from html import escape

from . import chart, journal
from .report import CURRENCY_ORDER, fmt_money, month_name, prev_month

ZERO = Decimal(0)
SOURCES = {"cli": "terminal", "phone": "phone", "claude": "Claude", "bank": "bank import"}

# colors (light theme; a dark override sits in the <style> block for clients that support it)
PAGE, CARD, LINE = "#f0efec", "#fcfcfb", "rgba(120,118,110,.25)"  # LINE reads on light and dark
INK, INK_2, INK_3 = "#0b0b0b", "#52514e", "#8a8984"
BAR, TRACK = "#2a78d6", "#eef3fa"
HEAT = ["#f0efec", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # nothing → most (blue ramp)
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def pretty(note: str, limit: int = 34) -> str:
    """Display form of a note: no bank leftovers, no repeated words, names capitalised.
    "google google one support.googl" → "Google One Support.googl", "kchuch dilijan" → "Kchuch Dilijan"."""
    ws = [w for w in (re.sub(r"\d{5,}", "", w) for w in note.split()) if w]  # terminal / account numbers
    ws = [w for i, w in enumerate(ws) if w.lower() not in (x.lower() for x in ws[:i])]
    if ws and ws[0].lower() == "visa":
        ws = ws[1:]
    while len(ws) > 1 and re.fullmatch(r"\d{1,3}|am|.|վիրտ\S*|yereva?n?", ws[-1], re.I):
        ws.pop()
    text = " ".join(w[:1].upper() + w[1:] if w.isascii() else w for w in ws) or note
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def money(amount: Decimal, cur: str) -> str:
    return f"{fmt_money(amount, cur)} {cur}"


def sum_by(entries, key) -> dict:
    out: dict = defaultdict(Decimal)
    for e in entries:
        out[key(e)] += e.amount
    return out


@dataclass
class Digest:
    ym: str
    month: list[journal.Entry]            # this month, every currency
    last: list[journal.Entry]             # last month
    every: list[journal.Entry]
    problem: str | None = None
    curs: list[str] = field(init=False)
    main: str = field(init=False)

    def __post_init__(self):
        totals = sum_by(self.month, lambda e: e.currency)
        self.curs = [c for c in CURRENCY_ORDER if c in totals] + sorted(set(totals) - set(CURRENCY_ORDER))
        self.main = self.curs[0] if self.curs else "AMD"

    @classmethod
    def build(cls, ym: str, every: list[journal.Entry], problem: str | None = None) -> "Digest":
        return cls(ym, [e for e in every if e.date.startswith(ym)],
                   [e for e in every if e.date.startswith(prev_month(ym))], every, problem)

    # numbers ---------------------------------------------------------------------------------
    def of(self, cur: str, entries=None) -> list[journal.Entry]:
        return [e for e in (self.month if entries is None else entries) if e.currency == cur]

    def total(self, cur: str, entries=None) -> Decimal:
        return sum((e.amount for e in self.of(cur, entries)), ZERO)

    def categories(self, cur: str) -> list[tuple[str, Decimal]]:
        return sorted(sum_by(self.of(cur), lambda e: e.category).items(), key=lambda kv: (-kv[1], kv[0]))

    def days(self) -> dict[int, Decimal]:
        return sum_by(self.of(self.main), lambda e: int(e.date[8:10]))

    def top(self, cur: str, n: int = 5) -> list[journal.Entry]:
        return sorted(self.of(cur), key=lambda e: -e.amount)[:n]

    def trend(self, n: int = 6) -> list[tuple[str, Decimal]]:
        months = chart.months_back(self.ym, n)
        per = sum_by(self.of(self.main, self.every), lambda e: e.date[:7])
        return [(m, per.get(m, ZERO)) for m in months]

    @property
    def days_in_month(self) -> int:
        y, m = map(int, self.ym.split("-"))
        return calendar.monthrange(y, m)[1]

    @property
    def subject(self) -> str:
        spent = " + ".join(money(self.total(c), c) for c in self.curs) or "nothing logged"
        return f"Spending · {month_name(self.ym)}: {spent}"

    def delta(self) -> str | None:
        """"12% more than August (+60,000 AMD)" for the main currency, if last month has data."""
        now, before = self.total(self.main), self.total(self.main, self.last)
        if not before:
            return None
        diff = now - before
        pct = round(abs(float(diff) / float(before)) * 100)
        word = "more" if diff > 0 else "less"
        sign = "+" if diff > 0 else "−"
        return f"{pct}% {word} than {month_name(prev_month(self.ym), '%B')} ({sign}{money(abs(diff), self.main)})"

    def highlights(self) -> list[str]:
        """Plain sentences; **bold** marks the key number (bold in HTML, stripped in text)."""
        if not self.month:
            return [f"Nothing was logged in {month_name(self.ym, '%B')}."]
        out, cur = [], self.main
        cats = self.categories(cur)
        total = self.total(cur)
        if cats:
            name, amount = cats[0]
            out.append(f"Most went to **{name}**: {money(amount, cur)}, "
                       f"{round(float(amount) / float(total) * 100)}% of everything in {cur}.")
        big = max(self.month, key=lambda e: (e.currency == cur, e.amount))
        out.append(f"Biggest single payment: **{money(big.amount, big.currency)}**, {pretty(big.note)} "
                   f"({big.category}, {date.fromisoformat(big.date):%b %-d}).")
        days = self.days()
        if days:
            d = max(days, key=lambda k: days[k])
            when = date.fromisoformat(f"{self.ym}-{d:02d}")
            out.append(f"Biggest day: **{when:%A, %b %-d}**, {money(days[d], cur)}.")
        subs = [e for e in self.month if e.category == "subscriptions"]
        if subs:
            by = sum_by(subs, lambda e: e.currency)
            per = " + ".join(money(by[c], c) for c in self.curs if c in by)
            names = list(dict.fromkeys(pretty(e.note, 18).split()[0] for e in subs))[:4]
            out.append(f"Subscriptions: **{per}** ({', '.join(names)}).")
        other = [e for e in self.of(cur) if e.category == "other"]
        if other:
            out.append(f"**{len(other)} payment{'s' if len(other) > 1 else ''}** "
                       f"({money(sum(e.amount for e in other), cur)}) still uncategorized: fix with `spend fix`.")
        delta = self.delta()
        out.append(f"That's {delta}." if delta else
                   f"First month with data: next month's report compares with {month_name(self.ym, '%B')}.")
        return out

    def footer(self) -> str:
        src = Counter((e.tags.partition("src:")[2].split(",")[0].strip() or "cli") for e in self.month)
        parts = ", ".join(f"{n} from {SOURCES.get(s, s)}" for s, n in src.most_common())
        return f"{len(self.month)} payments ({parts}). Sent by spend on {date.today():%b %-d, %Y}." if self.month \
            else f"Sent by spend on {date.today():%b %-d, %Y}."


# text ------------------------------------------------------------------------------------------
def render_text(d: Digest) -> str:
    out = [d.subject, ""]
    if d.problem:
        out += [f"⚠ {d.problem}; phone entries since your last `spend month` may be missing.", ""]
    out += ["• " + h.replace("**", "") for h in d.highlights()] + [""]
    for cur in d.curs:
        out.append(chart.render_bars(d.ym, cur, d.of(cur)))
    if d.main in d.curs:
        out.append(chart.render_days(d.ym, d.main, d.of(d.main)))
    for cur in d.curs:
        out.append(chart.render_top(d.ym, 5, cur, d.of(cur)).replace("biggest", "biggest payments,"))
    if sum(1 for _, v in d.trend() if v) >= 2:
        out.append(chart.render_trend(d.ym, 6, d.main, d.of(d.main, d.every)))
    out.append(d.footer())
    return "\n".join(out) + "\n"


# HTML ------------------------------------------------------------------------------------------
def _t(text: str) -> str:
    """Escape, then **bold** and `code`."""
    s = escape(text)
    s = re.sub(r"\*\*(.+?)\*\*", rf'<b style="color:{INK};font-weight:600" class="ink">\1</b>', s)
    return re.sub(r"`(.+?)`", r'<code style="font-family:Menlo,Consolas,monospace;font-size:12px;'
                              rf'background:{PAGE};color:{INK};padding:1px 4px;border-radius:4px;white-space:nowrap" '
                              r'class="chip">\1</code>', s)


def _h2(title: str, note: str = "") -> str:
    sub = f'<span style="color:{INK_3};font-weight:400"> · {escape(note)}</span>' if note else ""
    return (f'<tr><td style="padding:28px 28px 10px;font:600 15px/1.3 {FONT};color:{INK}" class="ink">'
            f"{escape(title)}{sub}</td></tr>")


def _bars(rows: list[tuple[str, Decimal]], cur: str) -> str:
    top, total = rows[0][1], sum(v for _, v in rows)
    trs = []
    for name, v in rows:
        w = max(1, round(float(v) / float(top) * 100))
        share = round(float(v) / float(total) * 100)
        trs.append(
            f'<tr><td style="padding:3px 10px 3px 0;font:400 14px/1.3 {FONT};color:{INK};white-space:nowrap" class="ink">{escape(name)}</td>'
            f'<td width="100%" style="padding:3px 0"><table role="presentation" width="{w}%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="background:{BAR};height:12px;border-radius:0 4px 4px 0;font-size:0;line-height:0" class="bar">&nbsp;</td></tr></table></td>'
            f'<td style="padding:3px 0 3px 12px;font:600 14px/1.3 {FONT};color:{INK};text-align:right;white-space:nowrap;'
            f'font-variant-numeric:tabular-nums" class="ink">{fmt_money(v, cur)}</td>'
            f'<td style="padding:3px 0 3px 10px;font:400 13px/1.3 {FONT};color:{INK_3};text-align:right;white-space:nowrap;'
            f'font-variant-numeric:tabular-nums">{share}%</td></tr>')
    return (f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            + "".join(trs) + "</table></td></tr>")


def _calendar(d: Digest) -> str:
    y, m = map(int, d.ym.split("-"))
    days = d.days()
    top = max(days.values(), default=ZERO)

    def step(v: Decimal) -> int:
        return 0 if v <= 0 or not top else min(5, 1 + int(float(v) / float(top) * 5 - 1e-9))

    head = "".join(f'<td style="padding:0 0 6px;font:600 11px {FONT};color:{INK_3};text-align:center">{w}</td>'
                   for w in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"))
    rows = []
    for week in calendar.Calendar().monthdayscalendar(y, m):
        cells = []
        for day in week:
            if not day:
                cells.append('<td style="padding:2px"></td>')
                continue
            v = days.get(day, ZERO)
            s = step(v)
            fg = "#ffffff" if s >= 3 else (INK if s else INK_3)
            tip = f"{month_name(d.ym, '%b')} {day}: {money(v, d.main)}" if v else f"{month_name(d.ym, '%b')} {day}: nothing"
            cells.append(f'<td style="padding:2px"><div title="{escape(tip)}" class="heat{s}" style="background:{HEAT[s]};color:{fg};'
                         f'border-radius:6px;height:38px;font:600 12px/38px {FONT};text-align:center">{day}</div></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    legend = "".join(f'<td style="padding:0 2px"><div class="heat{i}" style="background:{c};width:18px;height:10px;'
                     f'border-radius:3px;font-size:0;line-height:0">&nbsp;</div></td>' for i, c in enumerate(HEAT))
    return (f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="table-layout:fixed"><tr>{head}</tr>{"".join(rows)}</table>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:8px"><tr>'
            f'<td style="padding-right:6px;font:400 12px {FONT};color:{INK_3}" class="ink3">nothing</td>{legend}'
            f'<td style="padding-left:6px;font:400 12px {FONT};color:{INK_3}" class="ink3">most ({money(top, d.main)})</td>'
            f"</tr></table></td></tr>")


def _top(d: Digest) -> str:
    rows = []
    for cur in d.curs:
        for e in d.top(cur, 5 if cur == d.main else 3):
            rows.append(
                f'<tr><td style="padding:7px 10px 7px 0;border-top:1px solid {LINE};font:400 13px {FONT};color:{INK_3};'
                f'white-space:nowrap">{date.fromisoformat(e.date):%b %-d}</td>'
                f'<td style="padding:7px 10px 7px 0;border-top:1px solid {LINE};font:400 14px {FONT};color:{INK}" class="ink">'
                f'{escape(pretty(e.note))}<br><span style="font-size:12px;color:{INK_3}" class="ink3">{escape(e.category)}</span></td>'
                f'<td style="padding:7px 0;border-top:1px solid {LINE};font:600 14px {FONT};color:{INK};text-align:right;'
                f'white-space:nowrap;font-variant-numeric:tabular-nums" class="ink">{money(e.amount, cur)}</td></tr>')
    return (f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            + "".join(rows) + "</table></td></tr>")


def _trend(d: Digest) -> str:
    months = d.trend()
    top = max(v for _, v in months)
    rows = [(month_name(m, "%b"), v) for m, v in months]
    trs = "".join(
        f'<tr><td style="padding:3px 10px 3px 0;font:400 13px {FONT};color:{INK_2};white-space:nowrap">{name}</td>'
        f'<td width="100%" style="padding:3px 0">'
        + (f'<table role="presentation" width="{max(1, round(float(v) / float(top) * 100))}%" cellpadding="0" cellspacing="0">'
           f'<tr><td style="background:{BAR};height:10px;border-radius:0 4px 4px 0;font-size:0;line-height:0" class="bar">&nbsp;</td>'
           f"</tr></table>" if v else "")
        + f'</td><td style="padding:3px 0 3px 12px;font:400 13px {FONT};color:{INK_2};text-align:right;white-space:nowrap;'
          f'font-variant-numeric:tabular-nums">{fmt_money(v, d.main) if v else "–"}</td></tr>' for name, v in rows)
    return (f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f"{trs}</table></td></tr>")


def render_html(d: Digest) -> str:
    main_total = d.total(d.main)
    extra = " · ".join(f"+ {money(d.total(c), c)}" for c in d.curs[1:])
    delta = d.delta()
    spent_days = len(d.days())
    per_day = main_total / d.days_in_month if d.month else ZERO

    def stat(label: str, value: str) -> str:
        return (f'<td width="33%" style="padding:14px 16px;background:{PAGE};border-radius:10px" class="tile">'
                f'<div style="font:400 12px {FONT};color:{INK_2}" class="ink2">{label}</div>'
                f'<div style="font:600 18px/1.3 {FONT};color:{INK};margin-top:2px" class="ink">{value}</div></td>')

    body = [
        f'<tr><td style="padding:28px 28px 0;font:600 12px {FONT};color:{INK_2};letter-spacing:.06em;'
        f'text-transform:uppercase">Spending · {month_name(d.ym)}</td></tr>',
        f'<tr><td style="padding:6px 28px 0;font:600 46px/1.1 {FONT};color:{INK}" class="ink">'
        f'{fmt_money(main_total, d.main)} <span style="font-size:22px;color:{INK_2}" class="ink2">{d.main}</span></td></tr>',
    ]
    if extra:
        body.append(f'<tr><td style="padding:6px 28px 0;font:400 16px {FONT};color:{INK_2}" class="ink2">{escape(extra)}</td></tr>')
    if delta:
        body.append(f'<tr><td style="padding:6px 28px 0;font:400 14px {FONT};color:{INK_2}" class="ink2">{escape(delta)}</td></tr>')
    if d.month:
        body.append(
            f'<tr><td style="padding:20px 28px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{stat("Payments", str(len(d.month)))}<td style="width:8px"></td>'
            f'{stat("Per day, on average", money(per_day, d.main))}<td style="width:8px"></td>'
            f'{stat("Days you spent", f"{spent_days} of {d.days_in_month}")}</tr></table></td></tr>')
    if d.problem:
        body.append(f'<tr><td style="padding:16px 28px 0;font:400 14px {FONT};color:{INK}">⚠ {escape(d.problem)}; '
                    f"phone entries since your last <code>spend month</code> may be missing.</td></tr>")
    body.append(_h2("Highlights"))
    body.append(f'<tr><td style="padding:0 28px"><ul style="margin:0;padding:0 0 0 18px">'
                + "".join(f'<li style="margin:0 0 8px;font:400 14px/1.5 {FONT};color:{INK_2}" class="ink2">{_t(h)}</li>'
                          for h in d.highlights()) + "</ul></td></tr>")
    for cur in d.curs:
        cats = d.categories(cur)
        if cats:
            body.append(_h2("Where it went" if cur == d.main else f"Spent in {cur}",
                            f"{cur}, by category" if cur == d.main else ""))
            body.append(_bars(cats, cur))
    if d.days():
        body.append(_h2("Day by day", f"darker = more {d.main} spent"))
        body.append(_calendar(d))
    if d.month:
        body.append(_h2("Biggest payments"))
        body.append(_top(d))
    if sum(1 for _, v in d.trend() if v) >= 2:
        body.append(_h2("Last 6 months", d.main))
        body.append(_trend(d))
    body.append(f'<tr><td style="padding:28px 28px 28px;font:400 12px/1.5 {FONT};color:{INK_3}" class="ink3">'
                f"{escape(d.footer())}</td></tr>")

    heat_dark = ["#2a2a28", "#104281", "#1c5cab", "#2a78d6", "#5598e7", "#9ec5f4"]
    dark = ("@media (prefers-color-scheme: dark){"
            ".page{background:#111110!important}.card{background:#1a1a19!important}"
            ".ink{color:#ffffff!important}.ink2{color:#c3c2b7!important}.ink3{color:#9a9890!important}"
            ".tile{background:#262624!important}.bar{background:#3987e5!important}"
            ".chip{background:#2f2f2c!important;color:#e8e6df!important}"
            + "".join(f".heat{i}{{background:{c}!important;color:{'#0b0b0b' if i >= 4 else ('#ffffff' if i else '#9a9890')}!important}}"
                      for i, c in enumerate(heat_dark)) + "}")
    return ("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"color-scheme\" content=\"light dark\">"
            f"<meta name=\"viewport\" content=\"width=device-width\"><title>{escape(d.subject)}</title>"
            f"<style>{dark}</style></head>"
            f'<body style="margin:0;padding:0;background:{PAGE}" class="page">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE}" class="page">'
            f'<tr><td align="center" style="padding:24px 10px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="max-width:620px;background:{CARD};border-radius:14px" class="card">'
            + "".join(body) + "</table></td></tr></table></body></html>")
