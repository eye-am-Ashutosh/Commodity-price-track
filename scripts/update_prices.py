#!/usr/bin/env python3
"""Add the latest copper, lithium, WTI and Brent prices from tradingeconomics.com/commodities to data.json.

Run every weekday at 10:30 IST by .github/workflows/update-prices.yml (ESS Pricing Tracker). Each price is stored with Trading Economics'
own Day / Week / Month / Year % change and marked "TE". A date that already has an entry you
made yourself is never overwritten.
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://tradingeconomics.com/commodities"
SYMBOLS = {"HG1:COM": "copper", "LC:COM": "lithium", "CL1:COM": "wti", "CO1:COM": "brent"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DATA = Path(__file__).resolve().parent.parent / "data.json"


def fetch():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", "ignore")


def num(s):
    return float(s.replace(",", ""))


def price_date(label, today):
    """The table shows a time ("14:32") for today's quotes and "Sep/28" for earlier ones."""
    if re.match(r"^\d{1,2}:\d{2}", label):
        return today
    m = re.match(r"^([A-Za-z]{3})/(\d{1,2})$", label)
    if not m:
        return today
    month = MONTHS.index(m.group(1).title()) + 1
    return dt.date(today.year - (1 if month > today.month else 0), month, int(m.group(2)))


def parse(page, today):
    found = {}
    for symbol, key in SYMBOLS.items():
        row = re.search(r'<tr[^>]*data-symbol="' + re.escape(symbol) + r'"[^>]*>(.*?)</tr>', page, re.S)
        if not row:
            continue
        cells = row.group(1)
        price = re.search(r'id="p"[^>]*>\s*([\d.,]+)', cells)
        date = re.search(r'id="date"[^>]*>\s*([^<]+?)\s*<', cells)
        if not price:
            continue
        # data-value order: net change, day %, week %, month %, YTD %, year %
        values = [num(v) for v in re.findall(r'data-value="(-?[\d.,]+)"', cells)]
        pct = [round(values[i] / 100, 6) for i in (1, 2, 3, 5)] if len(values) >= 6 else [None] * 4
        found[key] = (price_date(date.group(1) if date else "", today), num(price.group(1)), pct)
    return found


MATCH = {"copper": r"copper", "lithium": r"lithium", "wti": r"\bwti\b|crude", "brent": r"brent"}


def targets(data):
    """Which dashboard section each price goes to: your own imported section with a matching
    name (e.g. "Crude Oil"), otherwise the built-in one — unless you've hidden it."""
    hidden = data.get("hiddenSections", {})
    own = sorted(data.get("sections", {}).items(), key=lambda kv: kv[1].get("order", 0))
    out = {}
    for builtin, pattern in MATCH.items():
        names = [k for k, s in own if s.get("segment") != "ess" and re.search(pattern, s.get("name", ""), re.I)
                 and not (builtin == "wti" and re.search("brent", s.get("name", ""), re.I))]
        if names:
            out[builtin] = names[0]
        elif builtin in data.get("sections", {}) and not hidden.get(builtin):
            out[builtin] = builtin
    return out


def main():
    today = dt.datetime.now(dt.timezone.utc).date()
    found = parse(fetch(), today)
    if not found:
        sys.exit("No prices found — the Trading Economics page may have changed or blocked the request.")

    data = json.loads(DATA.read_text()) if DATA.exists() else {}
    data.setdefault("sections", {})
    data.setdefault("hideSeed", {})
    data.setdefault("hiddenSections", {})
    rows = data.setdefault("rows", {})
    where = targets(data)

    changed = False
    for name, (date, price, pct) in found.items():
        key = where.get(name)
        if not key:
            print(f"{name}: skipped — there is no {name} row on this dashboard")
            continue
        label = data["sections"].get(key, {}).get("name", name)
        day = rows.setdefault(key, {})
        current = day.get(date.isoformat())
        if current and not (len(current) > 5 and current[5] == "TE"):
            print(f"{label}: {date} already has your own entry — left as is")
            continue
        new = [price, *pct, "TE"]
        if current != new:
            day[date.isoformat()] = new
            changed = True
        print(f"{label}: {date} {price}")

    if changed:
        data["savedAt"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        DATA.write_text(json.dumps(data, separators=(",", ":")))
    print("data.json updated" if changed else "No new prices")


if __name__ == "__main__":
    main()
