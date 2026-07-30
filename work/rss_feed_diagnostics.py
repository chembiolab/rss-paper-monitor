#!/usr/bin/env python3
"""Report per-feed freshness without changing monitor state or sending mail."""
import datetime as dt
import email.utils
import json
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = dt.timezone(dt.timedelta(hours=9))
state = json.loads((ROOT / "work/rss-paper-monitor-state.json").read_text(encoding="utf-8"))
since = dt.datetime.fromisoformat(state["last_successful_run"]).astimezone(KST)

def clean(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()

def published_at(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return (parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed).astimezone(KST)
    except Exception:
        match = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", value)
        return dt.datetime(*map(int, match.groups()), tzinfo=KST) if match else None

feeds = []
for line in (ROOT / "rss-feeds.md").read_text(encoding="utf-8").splitlines():
    if line.startswith("| ") and "http" in line:
        cells = [x.strip() for x in line.strip("|").split("|")]
        if len(cells) == 2 and cells[0] != "Source":
            feeds.append(cells)

results = []
for journal, url in feeds:
    row = {"journal": journal, "entries": 0, "dated_after_since": 0, "undated": 0}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ChembioLabMonitor/1.0 (jlee@sungshin.ac.kr)"})
        with urllib.request.urlopen(request, timeout=45, context=ssl.create_default_context()) as response:
            root = ET.fromstring(response.read())
        entries = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
        row["entries"] = len(entries)
        for entry in entries:
            values = []
            for name in ("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"):
                values.extend(clean("".join(node.itertext())) for node in entry.findall(name))
            published = next((published_at(value) for value in values if published_at(value)), None)
            if published is None:
                row["undated"] += 1
            elif published >= since:
                row["dated_after_since"] += 1
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    results.append(row)

print(json.dumps({"since": since.isoformat(), "feeds": results}, ensure_ascii=False, indent=2))
