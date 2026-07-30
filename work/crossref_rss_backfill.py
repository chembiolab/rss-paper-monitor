#!/usr/bin/env python3
"""Backfill monitored journal RSS with Crossref records missing from publisher feeds."""
import datetime as dt
import html
import json
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = dt.timezone(dt.timedelta(hours=9))
STATE_PATH = ROOT / "work/rss-paper-monitor-state.json"
RESULT_PATH = ROOT / "work/run-result.json"

# Registered print ISSNs for the scientific feeds. C&EN is intentionally absent.
JOURNAL_ISSNS = {
    "Chemical Science": "2041-6539",
    "Journal of the American Chemical Society": "0002-7863",
    "Journal of Medicinal Chemistry": "0022-2623",
    "ACS Medicinal Chemistry Letters": "1948-5875",
    "ACS Central Science": "2374-7943",
    "Cell Chemical Biology": "2451-9456",
    "JACS Au": "2691-3704",
    "Organic & Biomolecular Chemistry": "1477-0520",
    "Chemical Society Reviews": "1460-4744",
    "ACS Sensors": "2379-3694",
    "RSC Chemical Biology": "2633-0679",
    "Sensors & Diagnostics": "2635-0998",
    "Bioconjugate Chemistry": "1043-1802",
    "PNAS Chemistry": "0027-8424",
    "Angewandte Chemie International Edition": "1521-3773",
    "ACS Chemical Biology": "1554-8937",
    "Analytical Chemistry": "0003-2700",
}

def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()

def norm_url(url):
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))

def identities(paper):
    values = []
    if paper["doi"] != "DOI 없음":
        values.append(paper["doi"].lower())
    if paper.get("pmid"):
        values.append(str(paper["pmid"]).lower())
    if paper.get("url"):
        values.append(norm_url(paper["url"]).lower())
    values.append("title:" + re.sub(r"\W", "", paper["title"]).lower())
    return values

def labels(paper):
    haystack = (paper["title"] + " " + paper["abstract"]).lower()
    keys = {
        "serine protease": ["serine protease", "serine peptidase", "trypsin", "thrombin"],
        "cysteine protease": ["cysteine protease", "cysteine peptidase", "cathepsin"],
        "HTRA": ["htra", "htra1", "htra2", "htra3", "htra4"],
        "fluorescent probe": ["fluorescent probe", "fluorogenic", "fluorescence probe"],
        "activity-based probe": ["activity-based probe", "activity based probe", "activity-based profiling"],
        "peptide design": ["peptide design", "designed peptide", "peptide library"],
        "protein binder design": ["protein binder", "binder design", "binding protein"],
        "AI-driven peptide design": ["ai-driven peptide", "machine learning", "deep learning", "artificial intelligence"],
    }
    found = [topic for topic, terms in keys.items() if any(term in haystack for term in terms)]
    return found or ["기타"]

result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
last_success = dt.datetime.fromisoformat(result["since"]).astimezone(KST)
# Publisher feeds have been incomplete; always reconcile the last 48 hours once,
# while persistent DOI/URL de-duplication keeps repeat runs safe.
since = min(last_success, dt.datetime.now(KST) - dt.timedelta(hours=48))
seen = {str(value).lower() for value in state.get("seen_items", [])}
known = {identity for paper in result["items"] for identity in identities(paper)}
context = ssl.create_default_context()
backfill_counts = {}
errors = []

for journal, issn in JOURNAL_ISSNS.items():
    try:
        query = urllib.parse.urlencode({
            "filter": f"from-online-pub-date:{since:%Y-%m-%d},until-online-pub-date:{dt.datetime.now(KST):%Y-%m-%d},type:journal-article",
            "sort": "published",
            "order": "desc",
            "rows": 100,
        })
        request = urllib.request.Request(
            f"https://api.crossref.org/journals/{issn}/works?{query}",
            headers={"User-Agent": "ChembioLabMonitor/1.0 (jlee@sungshin.ac.kr)"},
        )
        with urllib.request.urlopen(request, timeout=45, context=context) as response:
            works = json.loads(response.read())["message"]["items"]
        added = 0
        for work in works:
            title = clean((work.get("title") or [""])[0])
            doi = work.get("DOI") or "DOI 없음"
            paper = {
                "source": "RSS 보강 수집 (Crossref)",
                "title": title,
                "journal": journal,
                "doi": doi,
                "pmid": "",
                "url": work.get("URL") or (f"https://doi.org/{doi}" if doi != "DOI 없음" else ""),
                "abstract": "초록 확인 불가",
                "authors": ", ".join(
                    " ".join(part for part in (author.get("family", ""), author.get("given", "")) if part)
                    for author in work.get("author", [])
                ) or "저자 정보 없음",
            }
            paper_ids = identities(paper)
            if not title or any(identity in seen or identity in known for identity in paper_ids):
                continue
            paper["labels"] = labels(paper)
            result["items"].append(paper)
            known.update(paper_ids)
            added += 1
        backfill_counts[journal] = added
    except Exception as exc:
        errors.append(f"Crossref 보강 {journal}: {type(exc).__name__}: {str(exc)[:140]}")

result["items"].sort(key=lambda paper: paper["title"].lower())
result["crossref_backfill_counts"] = backfill_counts
result["rss_backfill_added"] = sum(backfill_counts.values())
result["errors"].extend(errors)
result["new_seen"] = sorted({
    identity
    for paper in result["items"]
    for identity in identities(paper)
    if not identity.startswith("title:")
})
RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"rss_backfill_added": result["rss_backfill_added"], "errors": errors}, ensure_ascii=False))
