# iPhone Shortcut: log an expense from the phone

The Shortcut asks for one line ("800dram supermarket"), puts the time in front of it and appends it
to a text file in iCloud Drive. On the Mac, `spend inbox` imports the new lines into the journal,
tagged `src:phone`. No app, no server: just a text file that iCloud syncs.

```
iPhone Shortcut ──append──▶ iCloud Drive › Spend › inbox.txt ──`spend inbox`──▶ spend.journal
```

Each line in the inbox looks like this:

```
2026-10-04 14:32:05 800dram supermarket
```

## 1. Once, before building it

1. iPhone: iCloud Drive is on (Settings › your name › iCloud › iCloud Drive).
2. iPhone, **Files** app › Browse › **iCloud Drive**: make a folder named **`Spend`**
   (pull down or long-press an empty spot › New Folder).
3. Mac: same Apple ID, iCloud Drive on. The folder shows up in Finder as iCloud Drive › Spend, which is
   `~/Library/Mobile Documents/com~apple~CloudDocs/Spend/`, the path `spend inbox` reads by default.

## 2. Build the Shortcut

Shortcuts app › **+** › name it **Spend**. Add these 6 actions in this order (type the name in
"Search Actions"):

| # | Action | Set it to |
|---|---|---|
| 1 | **Ask for Input** | Input type: **Text**. Prompt: `Spent?` (leave Default Answer empty) |
| 2 | **Date** (shows as "Current Date") | leave as **Current Date** |
| 3 | **Format Date** | Date: **Current Date** (from step 2). Date Format: **Custom**. Format String: `yyyy-MM-dd HH:mm:ss` |
| 4 | **Text** | type: the **Formatted Date** variable, one space, then the **Provided Input** variable (tap in the box, pick each from the bar above the keyboard) |
| 5 | **Append to Text File** | Text: **Text** (from step 4). Folder: tap **Shortcuts** and pick **iCloud Drive › Spend**. File Path: `inbox.txt`. **Make New Line: on** |
| 6 | **Show Notification** | Body: `Logged: ` then the **Provided Input** variable |

Watch the format string: lowercase `yyyy` (capital `YYYY` is the week-year and goes wrong around
New Year), capital `MM` (month; `mm` is minutes) and capital `HH` (24-hour clock).

Step 4 must give exactly `2026-10-04 14:32:05 800dram supermarket`: the timestamp first, one space,
then what you typed. `spend inbox` also accepts the phone's default short style (`04.10.26, 18:18`, day first) and **ISO 8601** (with time) if you pick
that in step 3 instead of Custom.

### Check it once

Run the Shortcut, type `100 shortcut test`, then in Files open iCloud Drive › Spend: `inbox.txt`
should be there. On the Mac:

```sh
spend -n inbox     # should say: would log 100 AMD · … · shortcut test (…, phone)
```

If the file landed in **iCloud Drive › Shortcuts** instead (some iOS versions ignore the folder
choice), move it to the Spend folder and fix step 5, or point `spend` at it with
`export SPEND_INBOX="$HOME/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/inbox.txt"`
in `~/.zshrc`.

## 3. Make it one tap away

Pick any of these:

- **Home Screen:** open the Shortcut › Share (↑) › Add to Home Screen.
- **Action Button** (iPhone 15 Pro and later): Settings › Action Button › Shortcut › Spend.
- **Back Tap:** Settings › Accessibility › Touch › Back Tap › Double Tap › Spend.
- **Siri:** "Hey Siri, Spend", then say "eight hundred dram supermarket". Dictation types
  "800 dram supermarket", which `spend` reads fine.

## 4. On the Mac

`spend month` and `spend list` import new phone lines automatically. To import without a report:

```sh
spend inbox        # import new phone lines, tagged src:phone
spend -n inbox     # show what it would import, write nothing
```

- **Every line is imported exactly once.** `spend inbox` remembers a hash of every line it has handled
  (in `~/Desktop/personal/budgeting/.spend-inbox-state`), so running it again, iCloud duplicating a
  line or two runs at the same time never logs anything twice.
- It never changes `inbox.txt`. You can clear or delete the inbox in Files whenever you like.
- The expense date is the timestamp's date, so a line typed at 23:50 and imported tomorrow still
  counts for the right day. "yesterday" in the line counts back from the timestamp.
- One line can hold several expenses: `800dram supermarket, 50usd jeans`.
- Catching up on past days: `oct 1 1200 taxi, 4500 sas, oct 2 3000 coffee`. A date applies to the
  items after it until the next date; items with no date get the day you typed them.
- A line it can't read (no amount, like `coffee`) is printed once with the reason and then skipped
  for good: log it by hand, e.g. `spend 2026-10-04 300 coffee`.

## Troubleshooting

| You see | Do this |
|---|---|
| `no inbox at … yet` | The Shortcut hasn't run yet, or wrote somewhere else: see "Check it once". |
| A line you just logged isn't imported | iCloud can take a few seconds to a minute. Open iCloud Drive › Spend in Finder to nudge it, then run `spend inbox` again. |
| `… is still downloading from iCloud` | "Optimize Mac Storage" had moved the file to the cloud; `spend` has asked for it. Run again in a moment. |
| `inbox 2.txt` next to `inbox.txt` (a sync conflict) | `SPEND_INBOX=~/Library/Mobile\ Documents/com~apple~CloudDocs/Spend/inbox\ 2.txt spend inbox`, then delete it. Lines already imported are skipped. |
| `no timestamp at the start` | Step 3 or 4 is off: the line must start with `YYYY-MM-DD HH:MM:SS`. |
