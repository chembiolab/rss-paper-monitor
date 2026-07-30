#!/usr/bin/env python3
"""Collect new papers from PubMed only."""
import datetime as dt
import html
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
TOPICS = ["serine protease", "cysteine protease", "HTRA", "fluorescent probe", "activity-based probe", "peptide design", "protein binder design", "AI-driven peptide design"]
STATE_PATH = ROOT / "work/rss-paper-monitor-state.json"
state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
try:
    since = dt.datetime.fromisoformat(state["last_successful_run"]).astimezone(KST)
except Exception:
    since = NOW - dt.timedelta(days=1)
seen = {str(x).lower() for x in state.get("seen_items", [])}
context = ssl.create_default_context()
last_request = 0.0

def get(url):
    global last_request
    for attempt in range(4):
        wait = 0.45 - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        last_request = time.monotonic()
        request = urllib.request.Request(url, headers={"User-Agent": "ChembioLabMonitor/1.0 (jlee@sungshin.ac.kr)"})
        try:
            with urllib.request.urlopen(request, timeout=45, context=context) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))

def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()

def identities(paper):
    result = []
    if paper["doi"] != "DOI 없음":
        result.append(paper["doi"].lower())
    if paper.get("pmid"):
        result.append(str(paper["pmid"]).lower())
    if paper.get("url"):
        result.append(paper["url"].rstrip("/").lower())
    result.append("title:" + re.sub(r"\W", "", paper["title"]).lower())
    return result

def labels(paper):
    haystack = (paper["title"] + " " + paper["abstract"]).lower()
    terms = {
        "serine protease": ["serine protease", "serine peptidase", "trypsin", "thrombin"],
        "cysteine protease": ["cysteine protease", "cysteine peptidase", "cathepsin"],
        "HTRA": ["htra", "htra1", "htra2", "htra3", "htra4"],
        "fluorescent probe": ["fluorescent probe", "fluorogenic", "fluorescence probe"],
        "activity-based probe": ["activity-based probe", "activity based probe", "activity-based profiling"],
        "peptide design": ["peptide design", "designed peptide", "peptide library"],
        "protein binder design": ["protein binder", "binder design", "binding protein"],
        "AI-driven peptide design": ["ai-driven peptide", "machine learning", "deep learning", "artificial intelligence"],
    }
    found = list(paper.get("initial", []))
    for topic, words in terms.items():
        if topic not in found and any(word in haystack for word in words):
            found.append(topic)
    return found or ["기타"]

items, errors = [], []
pubmed_counts = {topic: 0 for topic in TOPICS}
successful_pubmed_queries = 0
for topic in TOPICS:
    try:
        term = f"({topic}) AND {since:%Y/%m/%d}:{NOW:%Y/%m/%d}[EDAT]"
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode({"db":"pubmed", "term":term, "retmax":100, "retmode":"json", "sort":"pub date"})
        ids = json.loads(get(search_url))["esearchresult"].get("idlist", [])
        successful_pubmed_queries += 1
        if not ids:
            continue
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode({"db":"pubmed", "id":",".join(ids), "retmode":"xml"})
        root = ET.fromstring(get(fetch_url))
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID", "")
            title_node = article.find(".//ArticleTitle")
            title = clean("".join(title_node.itertext())) if title_node is not None else ""
            abstract = " ".join(clean("".join(x.itertext())) for x in article.findall(".//Abstract/AbstractText")) or "초록 확인 불가"
            doi = next((x.text for x in article.findall(".//ArticleId") if x.get("IdType") == "doi" and x.text), "DOI 없음")
            authors = []
            for author in article.findall(".//Article/AuthorList/Author"):
                name = clean(author.findtext("CollectiveName", "")) or " ".join(x for x in (clean(author.findtext("LastName", "")), clean(author.findtext("Initials", ""))) if x)
                if name:
                    authors.append(name)
            paper = {"source":"PubMed", "title":title, "journal":clean(article.findtext(".//Journal/Title", "")), "doi":doi, "pmid":pmid, "url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "abstract":abstract, "initial":[topic], "authors":", ".join(authors) or "저자 정보 없음"}
            if title and not any(identity in seen for identity in identities(paper)):
                items.append(paper)
                pubmed_counts[topic] += 1
    except Exception as exc:
        errors.append(f"PubMed {topic}: {type(exc).__name__}: {str(exc)[:140]}")

unique = {}
for paper in items:
    if any(identity in unique for identity in identities(paper)):
        continue
    for identity in identities(paper):
        unique[identity] = paper
deduped, object_ids = [], set()
for paper in unique.values():
    if id(paper) not in object_ids:
        object_ids.add(id(paper))
        paper["labels"] = labels(paper)
        deduped.append(paper)
deduped.sort(key=lambda paper: paper["title"].lower())
result = {"run_at":NOW.isoformat(), "since":since.isoformat(), "pubmed_counts":pubmed_counts, "items":deduped, "errors":errors, "successful_pubmed_queries":successful_pubmed_queries, "collection_succeeded":bool(successful_pubmed_queries), "new_seen":sorted({value for paper in deduped for value in identities(paper) if not value.startswith("title:")})}
(ROOT/"work/run-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"count":len(deduped), "errors":errors, "pubmed_counts":pubmed_counts}, ensure_ascii=False))
