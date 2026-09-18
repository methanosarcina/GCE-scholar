"""Enrich ORCID-qualified records with DOI-matched lab images and OA figures.
Never adds a paper or infers authorship from a lab page. Images stay on source hosts.
"""
import argparse
import concurrent.futures
import datetime
import json
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
import collect

ROOT = Path(__file__).resolve().parent
DOI = re.compile(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', re.I)
LOCK = threading.Lock()

def canonical(value):
    match = DOI.search(urllib.parse.unquote(value or ''))
    if not match:
        return ''
    result = match.group(0).rstrip('.,;:').lower()
    while result.endswith(')') and result.count(')') > result.count('('):
        result = result[:-1]
    return result

def get_text(url):
    request = urllib.request.Request(url, headers={'User-Agent':'ScholarGallery/1.1 (public literature enrichment)'})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read(8_000_000)
        return payload.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')

def image_url(tag, base):
    src = tag.get('data-src') or tag.get('data-original') or tag.get('src') or ''
    if not src or src.startswith('data:'):
        return None
    url = urllib.parse.urljoin(base, src)
    if urllib.parse.urlparse(url).scheme != 'https':
        return None
    if re.search(r'logo|avatar|icon|portrait|banner|qrcode', url, re.I):
        return None
    return url

def identifiers(node):
    return {canonical(a.get('href')) for a in node.select('a[href]') if canonical(a.get('href'))}

def parse_lab(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup(['script','style','nav','header','footer']):
        node.decompose()
    records = {}
    for link in soup.select('a[href]'):
        doi = canonical(link['href'])
        if not doi:
            continue
        if doi not in records:
            records[doi] = {'doi':doi, 'source':url, 'figure':None}
        container = None
        # A single DOI and an image in a tight shared DOM block is unambiguous.
        for parent in list(link.parents)[:12]:
            if parent.name in ('body','html','[document]'):
                break
            if identifiers(parent) != {doi}:
                break
            if len(parent.get_text(' ', strip=True)) > 2400:
                break
            if parent.find('img'):
                container = parent
                break
        # Google Sites often puts an image-only section immediately after a citation.
        if container is None and 'sites.google.com' in url:
            section = link.find_parent('section')
            if section is not None and identifiers(section) == {doi}:
                following = section.find_next_sibling('section')
                if following and not following.get_text(' ',strip=True) and following.find('img'):
                    container = following
        if container is None:
            continue
        for tag in container.find_all('img'):
            image = image_url(tag,url)
            if image:
                records[doi]['figure'] = {'url':image, 'kind':'课题组配图', 'caption':tag.get('alt') or '课题组发表清单中与该 DOI 对应的配图。', 'source':url, 'provider':'lab', 'match':'exact-doi'}
                break
    return list(records.values())

def check_image(url):
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent':'ScholarGallery/1.1'})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.headers.get('Content-Type','').lower().startswith('image/')
    except Exception:
        return False

def save_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    temp.replace(path)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--all-oa', action='store_true', help='Inspect every remaining OA paper')
    parser.add_argument('--retry', action='store_true', help='Retry previously unsuccessful image extraction')
    parser.add_argument('--labs-only', action='store_true', help='Refresh official sources without inspecting OA full text')
    args=parser.parse_args()
    catalog=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf8'))
    scholars=json.loads((ROOT/'scholars.json').read_text(encoding='utf8'))
    sources=json.loads((ROOT/'lab_sources.json').read_text(encoding='utf8'))
    cache_path=ROOT/'data/enrichment.json'
    cache=json.loads(cache_path.read_text(encoding='utf8')) if cache_path.exists() else {'figures':{},'attempts':{}}
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    report={'updated':now,'sources':[], 'unmatched':[], 'policy':'Only existing ORCID-qualified papers may be enriched.'}
    by_doi={}
    unique={}
    for s in scholars:
        for paper in catalog['scholars'][s['id']]['papers']:
            unique.setdefault(paper['id'],paper)
            doi=canonical(paper.get('doi'))
            if doi:by_doi.setdefault(doi,[]).append(paper)
    def inspect_source(source):
        try:
            records=parse_lab(get_text(source['url']),source['url'])
            valid=0
            for record in records:
                fig=record['figure']
                if source.get('images',True) and fig and record['doi'] in by_doi:
                    if check_image(fig['url']):
                        fig['checkedAt']=now
                        with LOCK:
                            if cache['figures'].get(record['doi'],{}).get('kind') != '摘要图':
                                cache['figures'][record['doi']]=fig
                        valid+=1
                    else:record['figure']=None
            matched=sum(r['doi'] in by_doi for r in records)
            print(source['scholar'], 'DOIs',len(records),'matched',matched,'images',valid,flush=True)
            return source,records,{'status':'ok','doiCount':len(records),'matched':matched,'images':valid}
        except Exception as e:
            print(source['scholar'],'source unavailable',str(e)[:90],flush=True)
            return source,[],{'status':'unavailable','error':str(e)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for source,records,status in pool.map(inspect_source,sources):
            report['sources'].append({**source,**status})
            entry=catalog['scholars'][source['scholar']]
            entry['labSource']={**source,**status}
            for record in records:
                if record['doi'] not in by_doi:
                    report['unmatched'].append({'scholar':source['scholar'],'doi':record['doi'],'source':source['url'],'reason':'Not in current ORCID-qualified catalog; not automatically added'})
                for paper in by_doi.get(record['doi'],[]):
                    paper.setdefault('labSources',[])
                    if source['url'] not in paper['labSources']:paper['labSources'].append(source['url'])
    save_json(cache_path,cache)
    collect.fetch=get_text
    candidates=[p for p in unique.values() if p.get('oa') and p.get('pmcid') and not cache['figures'].get(canonical(p.get('doi'))) and not p.get('figure') and (args.retry or p['id'] not in cache['attempts'])]
    if not args.all_oa:candidates=candidates[:30]
    if args.labs_only:candidates=[]
    def inspect_pmc(paper):
        try:
            fig=collect.figure(paper['pmcid'])
            if fig and check_image(fig['url']):
                fig.update(provider='pmc',match='pmcid',checkedAt=now)
                return paper,fig,'found'
            return paper,None,'no_verified_image'
        except Exception as e:return paper,None,str(e)[:180]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for index,(paper,fig,status) in enumerate(pool.map(inspect_pmc,candidates),1):
            cache['attempts'][paper['id']]={'checkedAt':now,'status':status}
            if fig:cache['figures'][canonical(paper.get('doi')) or paper['id']]=fig
            if index%20==0:
                save_json(cache_path,cache)
                print('OA images checked',index,'/',len(candidates),flush=True)
    for entry in catalog['scholars'].values():
        for paper in entry['papers']:
            fig=cache['figures'].get(canonical(paper.get('doi')) or paper['id'])
            if fig and not ((paper.get('figure') or {}).get('provider') == 'publisher' or ((paper.get('figure') or {}).get('kind') == '摘要图' and fig.get('kind') != '摘要图')):
                paper['figure']=fig
        entry['imageCount']=sum(bool(p.get('figure')) for p in entry['papers'])
    # Shared papers must show the same best available image under every scholar.
    preferred={}
    rank={'摘要图':0,'课题组配图':1,'正文插图':2}
    for entry in catalog['scholars'].values():
        for paper in entry['papers']:
            fig=paper.get('figure')
            if fig and (paper['id'] not in preferred or rank.get(fig['kind'],3)<rank.get(preferred[paper['id']]['kind'],3)):
                preferred[paper['id']]=fig
    for entry in catalog['scholars'].values():
        for paper in entry['papers']:
            if paper['id'] in preferred:paper['figure']=preferred[paper['id']]
        entry['imageCount']=sum(bool(p.get('figure')) for p in entry['papers'])
    catalog['enrichedAt']=now
    report['summary']={'uniquePapers':len(unique),'withImages':sum(bool(p.get('figure')) for p in unique.values()),'labSources':len(sources),'successfulSources':sum(x['status']=='ok' for x in report['sources'])}
    previous_report=ROOT/'data/source-report.json'
    if previous_report.exists():
        previous=json.loads(previous_report.read_text(encoding='utf8'))
        for key in ('publisher','publisherAttempts'):
            if key in previous:report[key]=previous[key]
    save_json(cache_path,cache)
    save_json(ROOT/'data/source-report.json',report)
    save_json(ROOT/'data/catalog.json',catalog)
    print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':main()
