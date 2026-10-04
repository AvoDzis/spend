# spend

[![test](https://github.com/AvoDzis/spend/actions/workflows/test.yml/badge.svg)](https://github.com/AvoDzis/spend/actions/workflows/test.yml)

**Track spending by typing one line, from your terminal, your iPhone or Claude.**

```sh
$ spend 800dram supermarket, 50usd jeans
logged 800 AMD · groceries · supermarket (2026-10-04)
logged 50 USD · clothes · jeans (2026-10-04)
```

Most budgeting apps fail the same way: logging an expense takes a form, a category picker and a
sync, so after two weeks you stop. `spend` makes logging as cheap as a text message. You write what
you'd say out loud, and it works out the amount, the currency and the category. Your data stays in
one plain-text file on your machine: no account, no cloud, no subscription.

## How it's meant to be used

**Log right after you pay**, wherever you are:

| Where | What you do |
|---|---|
| Terminal | `spend 1200 taxi` |
| iPhone | tap the **Spend** Shortcut, type `4500 sas milk bread` |
| Claude Code | `/spend 300dram coffee`, or just "I spent 20 euros on a museum ticket" |

**Once a month (or whenever you're curious)**, look at where it went (example output):

```
$ spend month
October 2026
                        AMD    USD
  groceries          45,300      -
  eating-out         18,000      -
  transport          12,400      -
  clothes                 -  50.00
  ────────────────────────────────
  total              75,700  50.00
  last month (Sep)   81,200  30.00
```

**When it guesses a category wrong, fix it once** and it remembers:

```sh
spend fix last personal-care              # learns this note
spend fix last groceries --word sas       # learns just "sas", so "sas eggs" works next time
```

**Logged something by mistake?** `spend rm last`, or `spend rm 3` with the number from `spend list`.

## What it understands

- **Amounts anywhere:** `800 taxi`, `taxi 800`, `1,500 coffee`, `1.5k coffee`, `250k rent`
- **Currencies:** `800dram`, `800 amd`, `3000֏`, `50usd`, `$12.50`, `20eur`, `12€`, plus `rub` and `gbp`. No currency means AMD.
- **Several at once:** `800dram supermarket, 50usd jeans; 1200 taxi`
- **Other days:** `yesterday 1200 taxi`, `2026-09-30 5000 gym`
- **Categories:** 17 built-in ones (groceries, eating-out, transport, home, utilities, health,
  clothes, subscriptions…) matched by keyword, with Yerevan shops and services included.
  Anything unknown goes to `other` until you teach it.

Each currency gets its own column, with no conversion: the totals are exactly what you paid.

## Commands

```
spend <line>                        log one or more expenses
spend month [YYYY-MM]               totals by category, per currency, vs last month
spend list [N]                      last N entries (1 = newest)
spend fix last|N <cat> [--word kw]  re-tag an entry and learn the rule
spend learn <kw> <cat>              add a keyword rule
spend rm last|N [N …]               delete entries (asks first; -y skips it)
spend cats                          categories and their keywords
spend inbox                         import lines logged on the iPhone
spend -n …                          dry run: show, don't write
```

## How it works

```
iPhone Shortcut ─▶ iCloud Drive/Spend/inbox.txt ─▶ spend inbox ─┐
terminal: spend <line> ─────────────────────────────────────────┼─▶ spend.journal ─▶ spend month
Claude: /spend <line> ──────────────────────────────────────────┘     (hledger)
```

- **Storage is an [hledger](https://hledger.org) journal**, a plain-text accounting file. You can
  read it, grep it, back it up, or run any hledger report on it (`hledger -f spend.journal bal -M`).
- **The iPhone needs no app:** a small Shortcut appends a timestamped line to a text file in
  iCloud Drive. `spend inbox` imports each line exactly once, dated by when you typed it.
  Setup: [docs/phone-shortcut.md](docs/phone-shortcut.md).
- **Claude** uses the [`/spend` skill](claude/SKILL.md), which turns plain speech into a line
  and calls the CLI.
- About 800 lines of standard-library Python; the only other dependency is hledger.

## Install

```sh
brew install hledger
git clone <this repo> ~/Desktop/projects/spend && cd ~/Desktop/projects/spend
make install                          # links spend into ~/.local/bin (put that on your PATH)
make test
cp -r claude ~/.claude/skills/spend   # optional: the /spend skill for Claude Code
```

Data goes to `~/Desktop/personal/budgeting/` by default. Override it with `SPEND_DIR`, or per file
with `SPEND_JOURNAL`, `SPEND_RULES` and `SPEND_INBOX`.

**macOS:** to read the iCloud inbox, your terminal app needs Full Disk Access
(System Settings › Privacy & Security).

## Not included (on purpose)

Budgets, bank-statement import, currency conversion, any server or account. These may come later;
logging comes first.
