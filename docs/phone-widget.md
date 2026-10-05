# iPhone widget: see your spending on the phone

A Home Screen widget shows this month's total and top categories. Tap it for the full view:
today, yesterday, the last 7 days, this or last month, or pick any day or range of days, with every
payment grouped by day and by category (tap a category to see what's in it). ‹ › step back and
forward through months or day ranges.

It runs in [Scriptable](https://apps.apple.com/app/scriptable/id1405459188), a free app that runs
small scripts and widgets. Your Mac keeps it current: after every `spend` command, and every 30
minutes while the Mac is awake (`make schedule`), it writes the data and the widget's code into
Scriptable's iCloud folder. Nothing to copy by hand, and updates to the widget arrive the same way.

## Set it up once

1. **iPhone:** install **Scriptable** from the App Store and open it once (iCloud Drive must be on).
2. **Mac:** run `spend export`. It should say `updated Spend.js, spend-app.html, spend-data.json`.
   If it says "no Scriptable folder yet", wait a minute for iCloud and try again.
3. **iPhone:** in Scriptable you now see a script called **Spend**. Tap it: the full view opens.
4. **Add the widget:** long-press the Home Screen → **Edit** → **Add Widget** → **Scriptable** → pick
   a size (small: total + top 3; medium: top 4 with bars) → **Add Widget**. Then long-press the new
   widget → **Edit Widget** → **Script: Spend**, **When Interacting: Run Script**.

## Good to know

- Phone entries reach the widget after the Mac imports them (every 30 minutes while it's awake,
  or whenever you run `spend` there). The page's footer says when the data was last updated.
- Your data stays in your own iCloud Drive (Scriptable's folder); nothing goes to a server.
- The widget refreshes itself about every 15 minutes (iOS decides the exact moment).
