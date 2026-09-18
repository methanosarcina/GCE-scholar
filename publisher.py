"""Find only explicitly identified abstract graphics on public publisher pages.

DOIs select existing ORCID-qualified records. No authentication, challenge solving,
image URL guessing or replacement with unrelated social/first-figure images.
"""
import argparse
import collections
import concurrent.futures
import datetime
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
from collect import ROOT, matches_orcid
from enrich import canonical, save_json

LABEL = re.compile(r'graphical[\s_-]*abstract|visual[\s_-]*abstract|toc[\s_-]*(?:graphic|image)|abstract[\s_-]*(?:graphic|image)', re.I)
AGENT='ScholarGallery/1.2 (public publisher graphical abstract lookup)'
LOCK=threading.Lock()
HOSTS={}

def https_url(value, base):
    url=urllib.parse.urljoin(base,value or '')
    p=urllib.parse.urlparse(url)
    if p.scheme!='https' or not p.hostname or p.username or p.hostname in ('localhost','127.0.0.1','::1'):
        return None
    return url

def parse_publisher(html, source, doi):
    """Return evidence-backed candidates; reject contradictory article identity."""
    soup=BeautifulSoup(html,'html.parser')
    ids=set()
    for tag in soup.select('meta[content]'):
        name=(tag.get('name') or tag.get('property') or '').lower()
        if name in ('citation_doi','dc.identifier','dc.identifier.doi','prism.doi'):
            value=canonical(tag['content'])
            if value:ids.add(value)
    doi=canonical(doi)
    if ids and ids!={doi}:return [],'doi_mismatch'
    if not ids and canonical(source)!=doi:return [],'doi_not_verified'
    for tag in soup(['script','style','nav','header','footer']):tag.decompose()
    candidates=[]
    seen=set()
    for img in soup.find_all('img'):
        label=' '.join([img.get('alt',''),img.get('id',''),' '.join(img.get('class',[]))])
        evidence=LABEL.search(label)
        evidence=evidence.group(0) if evidence else None
        # Inspect tight semantic blocks, never a whole article containing both a
        # graphical-abstract heading and unrelated body figures.
        for parent in list(img.parents)[:8]:
            if parent.name in ('article','main','body','html','[document]'):break
            attrs=' '.join([parent.get('id',''),' '.join(parent.get('class',[]))])
            text=parent.get_text(' ',strip=True)
            if len(text)>4500 or len(parent.find_all('img'))>3:break
            hit=LABEL.search(attrs)
            heading=parent.find(re.compile('^h[1-6]$'),recursive=False)
            if hit or (heading and LABEL.search(heading.get_text(' ',strip=True))):
                evidence=hit.group(0) if hit else heading.get_text(' ',strip=True)
                break
            if re.search(r'^(?:Abs\d+-content|abstract)$',parent.get('id',''),re.I) or re.search(r'(?:^|[\s_-])abstract(?:$|[\s_-])',attrs,re.I):
                # An abstract may also contain inline equations or a body-figure
                # thumbnail. Require a semantic figure inside this abstract.
                figure=img.find_parent('figure')
                caption=figure.find('figcaption') if figure else None
                description=label+' '+(caption.get_text(' ',strip=True) if caption else '')
                if figure and parent in figure.parents and not re.search(r'\b(?:fig(?:ure)?\.?\s*\d|equation|formula|math|author|portrait)\b',description,re.I):
                    evidence='Image inside publisher abstract section'
                break
        if not evidence:continue
        src=img.get('data-src') or img.get('data-original') or img.get('src')
        url=https_url(src,source)
        if not url or url in seen or re.search(r'logo|avatar|icon|banner|portrait',url,re.I):continue
        seen.add(url)
        candidates.append({'url':url,'kind':'摘要图','caption':'出版社原文摘要配图。',
            'source':source,'provider':'publisher','match':'exact-doi','doi':doi,
            'evidence':evidence,'publisherLabel':evidence})
    return candidates,'found_candidates' if candidates else 'no_graphic_detected'

def host_state(host):
    with LOCK:
        return HOSTS.setdefault(host,{'semaphore':threading.Semaphore(2),'denials':0,'blocked':False})

class AccessDeferred(Exception):pass

class PoliteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # Legacy DOI records still point at HTTP article URLs. Use the same
        # publisher host/path over HTTPS, with certificate validation intact.
        if newurl.startswith('http://'):newurl='https://'+newurl[len('http://'):]
        url=https_url(newurl,req.full_url)
        if not url:raise ValueError('Non-HTTPS redirect')
        if host_state(urllib.parse.urlparse(url).hostname)['blocked']:
            raise AccessDeferred('Publisher host previously returned access restriction')
        return super().redirect_request(req,fp,code,msg,headers,url)

def fetch_page(url):
    host=urllib.parse.urlparse(url).hostname
    state=host_state(host)
    with state['semaphore']:
        if state['blocked']:raise AccessDeferred('Publisher host previously returned access restriction')
        try:
            req=urllib.request.Request(url,headers={'User-Agent':AGENT})
            with urllib.request.build_opener(PoliteRedirect()).open(req,timeout=20) as r:
                if 'html' not in r.headers.get('Content-Type',''):
                    return '',r.url
                html=r.read(6_000_000).decode(r.headers.get_content_charset() or 'utf8',errors='replace')
                final=r.url
            # Elsevier DOI pages sometimes have an ordinary meta-refresh redirect.
            if 'linkinghub.elsevier.com' in final:
                s=BeautifulSoup(html,'html.parser')
                field=s.find('input',id='redirectURL')
                if field:
                    target=https_url(urllib.parse.unquote(field.get('value','')),final)
                    if target and urllib.parse.urlparse(target).hostname in ('cell.com','www.cell.com','www.sciencedirect.com'):
                        return fetch_page(target)
            return html,final
        except urllib.error.HTTPError as e:
            if e.code in (401,403,429):
                denied=host_state(urllib.parse.urlparse(e.url).hostname)
                with LOCK:
                    denied['denials']+=1
                    if e.code==429 or denied['denials']>=2:denied['blocked']=True
            raise
        finally:time.sleep(.4)

def landing_url(doi):
    prefix,suffix=doi.split('/',1)
    if prefix=='10.1038':return 'https://www.nature.com/articles/'+suffix
    if prefix in ('10.1002','10.1111'):return 'https://onlinelibrary.wiley.com/doi/'+doi
    if prefix=='10.1021':return 'https://pubs.acs.org/doi/'+doi
    return 'https://doi.org/'+doi

def clean_source(url):
    p=urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,'',''))

def inspect(doi):
    source=landing_url(doi)
    try:
        html,source=fetch_page(source)
        if re.search(r'<title[^>]*>\s*(?:Just a moment|Access Denied|请稍候)',html,re.I):
            host_state(urllib.parse.urlparse(source).hostname)['blocked']=True
            return None,{'status':'access_restricted','source':source}
        candidates,status=parse_publisher(html,source,doi)
        for fig in candidates:
            try:
                req=urllib.request.Request(fig['url'],method='HEAD',headers={'User-Agent':AGENT})
                with urllib.request.urlopen(req,timeout=10) as r:
                    if r.headers.get('Content-Type','').lower().startswith('image/'):
                        return fig,{'status':'found','source':source}
            except Exception:pass
        return None,{'status':'image_unavailable' if candidates else status,'source':source}
    except AccessDeferred as e:return None,{'status':'host_deferred','source':source,'detail':str(e)}
    except urllib.error.HTTPError as e:
        return None,{'status':'access_restricted' if e.code in (401,403,429) else 'http_error','source':e.url,'httpStatus':e.code}
    except Exception as e:return None,{'status':'request_failed','source':source,'detail':str(e)[:160]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=0,help='0 checks all unattempted DOIs')
    parser.add_argument('--retry',action='store_true',help='Revisit previously unsuccessful attempts')
    parser.add_argument('--apply-only',action='store_true',help='Apply cached verified images without network requests')
    parser.add_argument('--retry-network',action='store_true',help='Retry only network/image failures, not access restrictions or parsed pages')
    args=parser.parse_args()
    catalog=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf8'))
    scholars=json.loads((ROOT/'scholars.json').read_text(encoding='utf8'))
    path=ROOT/'data/publisher-graphics.json'
    cache=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'figures':{},'attempts':{}}
    bydoi={}
    for s in scholars:
        for p in catalog['scholars'][s['id']]['papers']:
            if not matches_orcid(p,s['orcid']):raise ValueError('Catalog ORCID integrity failure')
            doi=canonical(p.get('doi'))
            if doi:bydoi.setdefault(doi,[]).append(p)
    todo=[d for d in bydoi if d not in cache['figures'] and (args.retry or d not in cache['attempts'] or (args.retry_network and cache['attempts'].get(d,{}).get('status') in ('request_failed','image_unavailable')))]
    # Distribute publishers across workers rather than queueing one blocked host.
    groups=collections.defaultdict(list)
    for d in todo:groups[d.split('/')[0]].append(d)
    todo=[]
    while any(groups.values()):
        for group in groups.values():
            if group:todo.append(group.pop(0))
    if args.limit:todo=todo[:args.limit]
    if args.apply_only:todo=[]
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    print('Publisher DOIs to inspect:',len(todo),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i,(doi,result) in enumerate(zip(todo,pool.map(inspect,todo)),1):
            fig,status=result
            cache['attempts'][doi]={**status,'checkedAt':now}
            if fig:
                fig['checkedAt']=now
                cache['figures'][doi]=fig
            if i%25==0:
                save_json(path,cache)
                print('Checked',i,'/',len(todo),'publisher graphics',len(cache['figures']),flush=True)
    for status in cache['attempts'].values():
        status['source']=clean_source(status['source'])
    for doi,fig in cache['figures'].items():
        fig['source']=clean_source(fig['source'])
        for p in bydoi.get(doi,[]):
            if p.get('figure') and p['figure'].get('provider')!='publisher':p['fallbackFigure']=p['figure']
            p['figure']=fig
    for entry in catalog['scholars'].values():
        entry['imageCount']=sum(bool(p.get('figure')) for p in entry['papers'])
    unique={p['id']:p for e in catalog['scholars'].values() for p in e['papers']}
    current_attempts={d:s for d,s in cache['attempts'].items() if d in bydoi}
    summary={'updated':max((x.get('checkedAt',now) for x in current_attempts.values()),default=now),
        'doiPapers':len(bydoi),'publisherGraphics':sum(d in bydoi for d in cache['figures']),
        'statuses':dict(collections.Counter(x['status'] for x in current_attempts.values()))}
    cache['summary']=summary
    catalog['publisherEnrichedAt']=now
    report_path=ROOT/'data/source-report.json'
    report=json.loads(report_path.read_text(encoding='utf8'))
    report['publisher']=summary
    report['summary']['withImages']=sum(bool(p.get('figure')) for p in unique.values())
    report['summary']['abstractGraphics']=sum((p.get('figure') or {}).get('kind')=='摘要图' for p in unique.values())
    report['publisherAttempts']=[{'doi':d,**s} for d,s in current_attempts.items()]
    save_json(path,cache)
    save_json(ROOT/'data/catalog.json',catalog)
    save_json(report_path,report)
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
