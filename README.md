# spend

Log an expense as one short line; it lands in an [hledger](https://hledger.org) journal.

```sh
spend 800dram supermarket, 50usd jeans
spend yesterday 1200 taxi
spend month
```

No currency means AMD. Data lives in `~/Desktop/personal/budgeting/` (override with `SPEND_DIR`,
`SPEND_JOURNAL`, `SPEND_RULES`, `SPEND_INBOX`). Run `spend help` for all commands.

- `make test`: run the tests (stdlib unittest; hledger needed for one test)
- `make install`: link `spend` into `~/.local/bin`
