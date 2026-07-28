#!/usr/bin/env python3
import datetime as dt, email.utils, html, json, re, ssl, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
TOPICS = ["serine protease", "cysteine protease", "HTRA", "fluorescent probe", "activity-based probe", "peptide design", "protein binder design", "AI-driven peptide design"]
STATE_PATH = ROOT / "work/rss-paper-monitor-state.json"
state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
try: since = dt.datetime.fromisoformat(state["last_successful_run"]).astimezone(KST)
except Exception: since = NOW - dt.timedelta(days=1)
seen = set(str(x).lower() for x in state.get("seen_items", []))
ctx = ssl.create_default_context()

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"ChembioLabMonitor/1.0 (jlee@sungshin.ac.kr)"})
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r: return r.read()
def clean(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def norm_url(url):
    p=urllib.parse.urlsplit(url); return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),p.query,''))
def date_from(value):
    if not value: return None
    try:
        x=email.utils.parsedate_to_datetime(value)
        return (x.replace(tzinfo=dt.timezone.utc) if x.tzinfo is None else x).astimezone(KST)
    except Exception: pass
    m=re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})",value)
    return dt.datetime(*map(int,m.groups()),tzinfo=KST) if m else None
def doi_from(s):
    m=re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",s,re.I)
    return m.group(0).rstrip(".,;)") if m else "DOI 없음"
def identities(p):
    out=[]
    if p['doi']!='DOI 없음': out.append(p['doi'].lower())
    if p.get('pmid'): out.append(str(p['pmid']).lower())
    if p.get('url'): out.append(norm_url(p['url']).lower())
    out.append('title:'+re.sub(r'\W','',p['title']).lower())
    return out
def labels(p):
    hay=(p['title']+' '+p['abstract']).lower(); out=list(p.get('initial',[]))
    keys={"serine protease":["serine protease","serine peptidase","trypsin","thrombin"],"cysteine protease":["cysteine protease","cysteine peptidase","cathepsin"],"HTRA":["htra","htra1","htra2","htra3","htra4"],"fluorescent probe":["fluorescent probe","fluorogenic","fluorescence probe"],"activity-based probe":["activity-based probe","activity based probe","activity-based profiling"],"peptide design":["peptide design","designed peptide","peptide library"],"protein binder design":["protein binder","binder design","binding protein"],"AI-driven peptide design":["ai-driven peptide","machine learning","deep learning","artificial intelligence"]}
    for name, words in keys.items():
        if name not in out and any(w in hay for w in words): out.append(name)
    return out or ['기타']
def assess(p):
    high=any(x in p['labels'] for x in ('HTRA','activity-based probe','serine protease','cysteine protease'))
    rel='높음' if high else ('중간' if p['labels']!=['기타'] else '낮음')
    first=re.split(r'(?<=[.!?])\s+',p['abstract'])[0][:420] if p['abstract']!='초록 확인 불가' else '초록이 제공되지 않아 제목과 서지정보를 바탕으로 핵심 주제를 확인했습니다.'
    sentences=[f"이 연구는 {first}", f"분류는 {', '.join(p['labels'])}이며 제목과 초록의 직접 키워드를 기준으로 판단했습니다.", "분자 기전, 검출 프로브 또는 설계 전략에서 후속 실험·문헌 검토의 단서를 제공합니다.", f"연구 관련성은 {rel}으로, " + ("표적 단백질분해효소 또는 활성 기반 분석과 직접 연결됩니다." if high else "현재 연구 축과의 방법론적 또는 주제적 접점을 반영했습니다.")]
    return ' '.join(sentences),rel

feeds=[]
for line in (ROOT/'rss-feeds.md').read_text().splitlines():
    if line.startswith('| ') and 'http' in line:
        c=[x.strip() for x in line.strip('|').split('|')]
        if len(c)==2 and c[0]!='Source': feeds.append(c)
items=[]; errors=[]; rss_counts={}; successful_rss_fetches=0; successful_pubmed_queries=0
for journal,url in feeds:
    added=0
    try:
        url = re.sub(r'^http:', 'https:', url)
        root=ET.fromstring(get(url)); successful_rss_fetches += 1; entries=root.findall('.//item')+root.findall('.//{http://www.w3.org/2005/Atom}entry')
        for e in entries:
            def find(*names): return next((clean(''.join(n.itertext())) for name in names for n in e.findall(name) if clean(''.join(n.itertext()))), '')
            title=find('title','{http://www.w3.org/2005/Atom}title'); published=date_from(find('pubDate','published','updated','{http://www.w3.org/2005/Atom}published','{http://www.w3.org/2005/Atom}updated'))
            link=find('link'); node=e.find('{http://www.w3.org/2005/Atom}link')
            if not link and node is not None: link=node.get('href','')
            abstract=find('description','summary','{http://www.w3.org/2005/Atom}summary','{http://purl.org/rss/1.0/modules/content/}encoded') or '초록 확인 불가'
            if not title or not link or (published and published < since): continue
            p={'source':'RSS','title':title,'journal':journal,'doi':doi_from(title+' '+abstract+' '+link),'pmid':'','url':link,'abstract':abstract}
            if not any(k in seen for k in identities(p)): items.append(p); added+=1
        rss_counts[journal]=added
    except Exception as ex: errors.append(f"RSS {journal}: {type(ex).__name__}: {str(ex)[:140]}")

pub_counts={t:0 for t in TOPICS}
for topic in TOPICS:
    try:
        term=f'({topic}) AND {since:%Y/%m/%d}:{NOW:%Y/%m/%d}[EDAT]'
        ep='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','term':term,'retmax':100,'retmode':'json','sort':'pub date'})
        ids=json.loads(get(ep))['esearchresult'].get('idlist',[]); successful_pubmed_queries += 1
        if not ids: continue
        xml=ET.fromstring(get('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','id':','.join(ids),'retmode':'xml'})))
        for a in xml.findall('.//PubmedArticle'):
            pmid=a.findtext('.//PMID',''); node=a.find('.//ArticleTitle'); title=clean(''.join(node.itertext())) if node is not None else ''
            abstract=' '.join(clean(''.join(x.itertext())) for x in a.findall('.//Abstract/AbstractText')) or '초록 확인 불가'
            doi=next((x.text for x in a.findall('.//ArticleId') if x.get('IdType')=='doi' and x.text),'DOI 없음')
            p={'source':'PubMed','title':title,'journal':clean(a.findtext('.//Journal/Title','')),'doi':doi,'pmid':pmid,'url':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/','abstract':abstract,'initial':[topic]}
            if title and not any(k in seen for k in identities(p)): items.append(p); pub_counts[topic]+=1
    except Exception as ex: errors.append(f"PubMed {topic}: {type(ex).__name__}: {str(ex)[:140]}")

unique={}
for p in items:
    if next((k for k in identities(p) if k in unique),None): continue
    for k in identities(p): unique[k]=p
seen_obj=set(); items=[p for p in unique.values() if not (id(p) in seen_obj or seen_obj.add(id(p)))]
for p in items: p['labels']=labels(p); p['summary'],p['relevance']=assess(p)
items.sort(key=lambda p:(p['relevance']!='높음',p['title'].lower()))
result={'run_at':NOW.isoformat(),'since':since.isoformat(),'rss_feed_count':len(feeds),'rss_counts':rss_counts,'pubmed_counts':pub_counts,'items':items,'errors':errors,'successful_rss_fetches':successful_rss_fetches,'successful_pubmed_queries':successful_pubmed_queries,'collection_succeeded':bool(successful_rss_fetches or successful_pubmed_queries),'new_seen':sorted({v for p in items for v in identities(p) if not v.startswith('title:')})}
(ROOT/'work/run-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'count':len(items),'errors':errors,'pubmed_counts':pub_counts},ensure_ascii=False))
