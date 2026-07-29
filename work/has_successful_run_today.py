#!/usr/bin/env python3
"""Exit successfully only when today's KST monitor run already succeeded."""
import datetime as dt
import json
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
STATE = Path("work/rss-paper-monitor-state.json")

try:
    last = dt.datetime.fromisoformat(json.loads(STATE.read_text(encoding="utf-8"))["last_successful_run"])
    if last.tzinfo is None:
        last = last.replace(tzinfo=dt.timezone.utc)
    completed_today = last.astimezone(KST).date() == dt.datetime.now(KST).date()
except Exception:
    completed_today = False

raise SystemExit(0 if completed_today else 1)
