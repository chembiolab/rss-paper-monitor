#!/usr/bin/env python3
import datetime as dt, html, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
r=json.loads((ROOT/'work/run-result.json').read_text(encoding='utf-8'))
today=dt.datetime.fromisoformat(r['run_at']).date().isoformat()
def esc(s): return html.escape(str(s or ''))
def link(url,label=None): return f'<a href="{esc(url)}">{esc(label or url)}</a>'
parts=[f'<h1>논문 모니터 — {today}</h1>', '<section class="summary"><h2>실행 요약</h2>',f'<p>실행 시각: {esc(r["run_at"])}</p>',f'<p>이전 성공 실행 기준: {esc(r["since"])}</p>',f'<p>확인 RSS 피드: {r["rss_feed_count"]}개 (성공 {r.get("successful_rss_fetches",0)}개)</p>',f'<p>RSS 신규 수집: {sum(r["rss_counts"].values())}건</p>','<p>PubMed 검색어별 수집 수:</p><ul>']
parts += [f'<li>{esc(k)}: {v}건</li>' for k,v in r['pubmed_counts'].items()]
parts += [f'</ul><p><strong>중복 제거 후 신규 논문: {len(r["items"])}건</strong></p></section>']
if r['errors']:
    parts += ['<section><h2>수집 오류</h2><ul>']+[f'<li>{esc(x)}</li>' for x in r['errors']]+['</ul></section>']
if not r['items']: parts.append('<section><h2>새 논문 없음</h2><p>이번 실행 기준으로 새 RSS·PubMed 논문이 없습니다.</p></section>')
for i,p in enumerate(r['items'],1):
    doi='DOI 없음' if p['doi']=='DOI 없음' else link('https://doi.org/'+p['doi'],p['doi'])
    pmid=esc(p['pmid']) if p['pmid'] else '해당 없음'
    parts += [f'<article><h2>{i}. {esc(p["title"])}</h2>',f'<p class="tags"><b>저널</b> {esc(p["journal"] or "확인 불가")} · <b>분류</b> {esc(", ".join(p["labels"]))} · <b>관련성</b> <mark class="{p["relevance"]}">{p["relevance"]}</mark></p>',f'<p><b>출처</b> {esc(p["source"])} · <b>DOI</b> {doi} · <b>PMID</b> {pmid}</p>',f'<p><b>원문 또는 PubMed</b> {link(p["url"])}</p>',f'<h3>초록</h3><p>{esc(p["abstract"])}</p>',f'<h3>한국어 요약 및 관련성 평가</h3><p>{esc(p["summary"])}</p></article>']
page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>논문 모니터</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;background:#f5f7fa;color:#17202a;line-height:1.65;margin:0}main{max-width:920px;margin:30px auto;padding:36px 44px;background:white;box-shadow:0 2px 16px #0001;border-radius:14px}h1{color:#12355b;border-bottom:3px solid #2673c9;padding-bottom:14px}h2{color:#174d83;margin-top:30px}article{border-top:1px solid #d9e2ec;padding-top:12px}a{color:#075bb5;word-break:break-all}.summary{background:#edf5ff;padding:12px 22px;border-radius:8px}.tags{font-size:1.03em}mark{padding:2px 7px;border-radius:5px;color:white}.높음{background:#b42318}.중간{background:#b26a00}.낮음{background:#4b5563}@media(max-width:640px){main{margin:0;padding:18px;border-radius:0}}</style></head><body><main>'''+''.join(parts)+'''</main></body></html>'''
out=ROOT/'outputs'/f'{today}.html'; out.parent.mkdir(exist_ok=True); out.write_text(page,encoding='utf-8')
state_path=ROOT/'work/rss-paper-monitor-state.json'; old=json.loads(state_path.read_text()) if state_path.exists() else {}
if r.get('collection_succeeded'):
    old_seen=set(str(x) for x in old.get('seen_items',[])); old_seen.update(r['new_seen'])
    state_path.write_text(json.dumps({'last_successful_run':r['run_at'],'seen_items':sorted(old_seen)},ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
