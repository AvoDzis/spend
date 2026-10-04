---
name: spend
description: Log and look up Avo's spending with the `spend` CLI (hledger journal in ~/Desktop/personal/budgeting/). Trigger on "/spend", "I spent…", "log 800dram supermarket", "how much did I spend this month", "spending summary", "import my phone expenses".
---

# spend — log and look up spending

`spend` is on PATH (`~/.local/bin/spend` → `~/Desktop/projects/spend/bin/spend`); if not found, call that path directly. Run `spend help` for the full usage.

| Avo says | Run |
|---|---|
| `/spend 800dram supermarket, 50usd jeans` | `spend --src claude 800dram supermarket, 50usd jeans` |
| "I spent 1200 on a taxi yesterday" | rewrite into the line format `[date] <amount><currency> <what>` first: `spend --src claude yesterday 1200 taxi` |
| `/spend month [YYYY-MM]`, "how much this month?" | `spend month [YYYY-MM]` (it imports new phone lines itself) |
| `/spend list [N]` | `spend list [N]` |
| `/spend chart …`, "show me a chart", "which days did I spend most" | `spend chart` (bars per category), `--trend N`, `--days`, `--cat <c>`, `--top N`, `--month YYYY-MM`, `--currency USD`; show the output in a code block |
| `/spend fix last eating-out`, "that was eating out" | `spend fix last eating-out` (or `spend fix N <cat>` with N from `spend list`) |
| `/spend rm last`, "delete that", "remove the taxi" | `spend -n rm last` (or `rm N` with N from `spend list`), show Avo what would go, and only after a yes: `spend rm -y …` with the same target |
| `/spend report [YYYY-MM]`, "month-end report" | `spend report [YYYY-MM]` (default: last month). `--email` sends it via Gmail; only when Avo asks |
| `/spend inbox` | `spend inbox` |
| "import my bank CSV for September" | `spend -n import <file> --month 2026-09` first, show the summary, then without `-n`. Only for months not logged by hand (else duplicates). |
| `/spend cats` | `spend cats` |

## Line format
`<amount><currency> <what>`, several separated by `, ` or `;`. No currency means AMD. Currencies: `dram`/`amd`/`֏`, `usd`/`$`, `eur`/`€`, `rub`, `gbp`. `1.5k` = 1500. Dates: `today` (default), `yesterday`, `YYYY-MM-DD`. Quote anything with `$` for the shell (`spend '$50 jeans'`), or write `50usd`.

## Rules
- Show the CLI's output lines as they are; they're short.
- If a line was logged as `other`, ask Avo once which category, then `spend fix last <cat>`: that also saves the rule for next time. By default it learns the whole note; when the note contains an obvious store or brand ("sas milk bread" → `sas`), add `--word <kw>` so the rule generalizes. `spend learn <kw> <cat>` adds a rule without an entry. For a one-off (a gift or cake from a shop normally filed elsewhere), use `spend fix N <cat> --once`: no rule is saved.
- A question the commands don't answer (e.g. "groceries in September", "biggest expenses") → query hledger read-only: `hledger -f "${SPEND_JOURNAL:-$HOME/Desktop/personal/budgeting/spend.journal}" bal expenses:groceries -p 2026-09` / `reg expenses -p thismonth`.
- Exit 2 = couldn't parse the line: show the message and ask, don't guess.
- Phone lines live in iCloud Drive, which Claude's Bash sandbox can block. If `spend month`/`list` says "phone entries not imported", or `spend inbox` says "permission denied", ask Avo to type `! spend inbox`, then continue.
- Never edit the journal by hand; use the CLI.
- **Private:** amounts and notes stay in the answer here. Never copy them into Obsidian notes, memory, the RAG index, or any external service.
