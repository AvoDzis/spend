// Spend: your spending on the iPhone.
// As a widget: this month's total and top categories. Tapped (or run): the full view, where you
// pick today / a day / a range of days and see every payment.
// The `spend` CLI on your Mac writes this script, the page (spend-app.html) and the data
// (spend-data.json) into Scriptable's iCloud folder and keeps them current. Edits here get
// overwritten; change phone/Spend.js in the spend repo instead.

const fm = FileManager.iCloud();
const dir = fm.documentsDirectory();

async function read(name) {
  const path = fm.joinPath(dir, name);
  if (!fm.fileExists(path)) return null;
  if (!fm.isFileDownloaded(path)) await fm.downloadFileFromiCloud(path);
  return fm.readString(path);
}

const raw = await read("spend-data.json");
const data = raw ? JSON.parse(raw) : { generated: new Date().toISOString(), entries: [] };

const MAIN = "AMD";
const pad = (n) => String(n).padStart(2, "0");
const now = new Date();
const thisMonth = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
const money = (v, c) => (c === "AMD" ? Math.round(v).toLocaleString("en-US") : v.toFixed(2));

// this month: [date, amount, currency, category, note, source]
const month = data.entries.filter((r) => r[0].startsWith(thisMonth));
const totals = {};
for (const r of month) totals[r[2]] = (totals[r[2]] || 0) + r[1];
const cats = {};
for (const r of month.filter((r) => r[2] === MAIN)) {
  const parent = r[3].split("/")[0];
  cats[parent] = (cats[parent] || 0) + r[1];
}
const top = Object.entries(cats).sort((a, b) => b[1] - a[1]);

const ink = Color.dynamic(new Color("#0b0b0b"), new Color("#ffffff"));
const ink2 = Color.dynamic(new Color("#52514e"), new Color("#c3c2b7"));
const bar = Color.dynamic(new Color("#2a78d6"), new Color("#3987e5"));
const track = Color.dynamic(new Color("#e6e4de"), new Color("#2a2a28"));
const card = Color.dynamic(new Color("#fcfcfb"), new Color("#1a1a19"));

function text(stack, value, font, color) {
  const t = stack.addText(value);
  t.font = font;
  t.textColor = color;
  t.lineLimit = 1;
  return t;
}

function buildWidget(family) {
  const w = new ListWidget();
  w.backgroundColor = card;
  w.setPadding(14, 14, 14, 14);
  w.url = URLScheme.forRunningScript();
  w.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);

  const monthName = now.toLocaleDateString("en-US", { month: "long" }).toUpperCase();
  const head = w.addStack();
  head.layoutVertically();
  text(head, monthName, Font.semiboldSystemFont(11), ink2);
  const totalLine = head.addStack();
  totalLine.bottomAlignContent();
  const total = text(totalLine, money(totals[MAIN] || 0, MAIN), Font.semiboldRoundedSystemFont(family === "small" ? 24 : 28), ink);
  total.minimumScaleFactor = 0.6;
  totalLine.addSpacer(4);
  text(totalLine, MAIN, Font.semiboldSystemFont(12), ink2);
  const others = Object.keys(totals).filter((c) => c !== MAIN).map((c) => `+${money(totals[c], c)} ${c}`);
  if (others.length) text(head, others.join(" · "), Font.systemFont(11), ink2);

  w.addSpacer(8);
  const rows = top.slice(0, family === "small" ? 3 : family === "medium" ? 4 : 8);
  const max = rows.length ? rows[0][1] : 1;
  const barWidth = family === "small" ? 120 : 280;
  for (const [name, value] of rows) {
    const line = w.addStack();
    line.layoutHorizontally();
    text(line, name, Font.systemFont(11), ink);
    line.addSpacer();
    text(line, money(value, MAIN), Font.semiboldSystemFont(11), ink);
    if (family !== "small") {
      w.addSpacer(2);
      const t = w.addStack();
      t.size = new Size(barWidth, 4);
      t.backgroundColor = track;
      t.cornerRadius = 2;
      t.layoutHorizontally();
      const fill = t.addStack();
      fill.size = new Size(Math.max(2, Math.round((value / max) * barWidth)), 4);
      fill.backgroundColor = bar;
      fill.cornerRadius = 2;
      t.addSpacer();
    }
    w.addSpacer(family === "small" ? 2 : 4);
  }
  if (!rows.length) text(w, "Nothing logged yet this month", Font.systemFont(11), ink2);
  w.addSpacer();
  return w;
}

if (config.runsInWidget) {
  Script.setWidget(buildWidget(config.widgetFamily || "small"));
} else {
  const page = await read("spend-app.html");
  if (!page) {
    const a = new Alert();
    a.title = "Spend isn't set up yet";
    a.message = "Run `spend export` on your Mac, wait a moment for iCloud, then try again.";
    a.addAction("OK");
    await a.present();
  } else {
    const view = new WebView();
    await view.loadHTML(page.replace("__SPEND_DATA__", JSON.stringify(data)));
    await view.present(true);
  }
}
Script.complete();
