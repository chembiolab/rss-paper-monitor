#!/usr/bin/env python3
"""Send the report from a GitHub-hosted runner using Gmail SMTP secrets."""
import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
result = json.loads((ROOT / "work/run-result.json").read_text(encoding="utf-8"))
run_date = result["run_at"][:10]
items = result["items"]
high = [p for p in items if p["relevance"] == "높음"]
subject = f"[논문 모니터] {run_date}" + (" (새 논문 없음)" if not items else "")

lines = [f"중복 제거 후 신규 논문: {len(items)}건", ""]
if high:
    lines.append("관련성 높음 논문")
    for p in high:
        one_line = p["summary"].split(". ", 1)[0].strip()
        lines.append(f"- {p['title']}: {one_line}")
else:
    lines.append("관련성 높음 논문: 없음")
if result.get("errors"):
    lines += ["", f"수집 오류: {len(result['errors'])}건 (첨부 보고서 참조)"]

msg = EmailMessage()
msg["Subject"] = subject
msg["From"] = os.environ["SMTP_USERNAME"]
msg["To"] = os.environ.get("MONITOR_RECIPIENT", "jlee@sungshin.ac.kr")
msg.set_content("\n".join(lines))
report = ROOT / "outputs" / f"{run_date}.html"
msg.add_attachment(report.read_bytes(), maintype="text", subtype="html", filename=report.name)

with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
    smtp.starttls()
    smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_APP_PASSWORD"])
    smtp.send_message(msg)
