"""Public literature metadata collector; Python 3.10+, standard library only."""
import argparse
import concurrent.futures
import datetime
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = 'https://www.ebi.ac.uk/europepmc/webservices/rest/'

def fetch(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'ScholarGallery/1.0 (public academic metadata)'})
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode('utf-8')
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def plain(value):
    value = html.unescape(value or '')
    value = re.sub(r'</?(?:sub|sup|i|b|em|strong)\b[^>]*>', '', value, flags=re.I)
    return re.sub('<[^>]+>', ' ', value).strip()

def orcid_query(orcid):
    if not re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', orcid or ''):
        raise ValueError('A fixed ORCID is required')
    return 'AUTHORID:"' + orcid + '"'

def matches_orcid(paper, orcid):
    return any(a.get('authorId', {}).get('type') == 'ORCID'
               and a['authorId'].get('value') == orcid
               for a in paper.get('authorDetails', []))

def normalize(p):
    return dict(id=p['source'] + ':' + p['id'], title=plain(p.get('title')), year=p.get('pubYear', ''),
                journal=p.get('journalInfo', {}).get('journal', {}).get('title', ''),
                abstract=plain(p.get('abstractText')), authors=p.get('authorString', ''),
                doi=p.get('doi', ''), pmcid=p.get('pmcid', ''), oa=p.get('isOpenAccess') == 'Y',
                citations=p.get('citedByCount', 0), license=p.get('license', ''),
                url='https://europepmc.org/article/' + p['source'] + '/' + p['id'],
                authorDetails=p.get('authorList', {}).get('author', []))

def search(query, cursor='*', size=36):
    data = json.loads(fetch(API + 'search?' + urllib.parse.urlencode(dict(
        query=query + ' sort_date:y', cursorMark=cursor, pageSize=size, resultType='core', format='json'))))
    papers = [normalize(p) for p in data.get('resultList', {}).get('result', [])]
    nxt = data.get('nextCursorMark')
    return dict(papers=papers, total=data.get('hitCount', 0), cursor=nxt if papers and nxt != cursor else None)

def figure(pmcid):
    if not re.fullmatch(r'PMC\d+', pmcid):
        raise ValueError('Invalid PMCID')
    root = ET.fromstring(fetch(API + pmcid + '/fullTextXML'))
    candidates = []
    for node in root.iter():
        if node.tag in ('fig', 'abstract'):
            graphics = list(node.iter('graphic'))
            if not graphics:
                continue
            caption = plain(' '.join(node.itertext()))
            graphical = node.get('abstract-type') == 'graphical' or 'graphical abstract' in caption.lower()
            href = graphics[0].get('{http://www.w3.org/1999/xlink}href', '')
            candidates.append((0 if graphical else 1, href, caption[:1200]))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    page = fetch('https://pmc.ncbi.nlm.nih.gov/articles/' + pmcid + '/')
    images = re.findall(r'<img\b[^>]*\bsrc=[\"\x27]([^\"\x27]+)', page, re.I)
    for priority, href, caption in candidates:
        stem = href.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        for src in images:
            if stem and stem in src.rsplit('/', 1)[-1] and ('/pmc/' in src):
                url = urllib.parse.urljoin('https://pmc.ncbi.nlm.nih.gov', html.unescape(src))
                if urllib.parse.urlparse(url).hostname not in ('cdn.ncbi.nlm.nih.gov', 'pmc.ncbi.nlm.nih.gov'):
                    continue
                return dict(url=url, kind='摘要图' if priority == 0 else '正文插图', caption=caption,
                            source='https://pmc.ncbi.nlm.nih.gov/articles/' + pmcid + '/')
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true', help='Retrieve all indexed matches; verify identities first')
    parser.add_argument('--resolved-all', action='store_true', help='Retrieve all pages only for scholars with an ORCID')
    parser.add_argument('--figures', type=int, default=4, help='Maximum OA articles to inspect per scholar')
    args = parser.parse_args()
    scholars = json.loads((ROOT / 'scholars.json').read_text(encoding='utf-8'))
    for scholar in scholars:
        scholar['query'] = orcid_query(scholar.get('orcid'))
    path = ROOT / 'data' / 'catalog.json'
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'scholars': {}}
    result = dict(updated=datetime.datetime.now(datetime.timezone.utc).isoformat(), scholars={})
    def one(s):
        try:
            entry = search(s['query'])
            seen = {p['id'] for p in entry['papers']}
            while entry['cursor']:
                page = search(s['query'], entry['cursor'])
                entry['papers'].extend(p for p in page['papers'] if p['id'] not in seen)
                seen.update(p['id'] for p in page['papers'])
                entry['cursor'] = page['cursor']
                time.sleep(.2)
            entry['papers'] = [p for p in entry['papers'] if matches_orcid(p, s['orcid'])]
            previous = old['scholars'].get(s['id'], {})
            preserved = {p['id']:p for p in previous.get('papers', [])}
            if previous.get('labSource'):
                entry['labSource'] = previous['labSource']
            budget = args.figures
            for p in entry['papers']:
                prior = preserved.get(p['id'], {})
                for key in ('figure', 'fallbackFigure', 'labSources'):
                    if prior.get(key):
                        p[key] = prior[key]
                if not p.get('figure') and p['pmcid'] and p['oa'] and budget > 0:
                    budget -= 1
                    try:
                        p['figure'] = figure(p['pmcid'])
                    except Exception:
                        p['figure'] = None
            entry['query'] = s['query']
            entry['orcid'] = s['orcid']
            entry['complete'] = not bool(entry['cursor'])
            entry['updated'] = result['updated']
            print(s['name'], len(entry['papers']), '/', entry['total'], flush=True)
        except Exception as exc:
            previous = old['scholars'].get(s['id'], {})
            entry = dict(previous) if previous.get('query') == s['query'] else {'papers': [], 'query': s['query'], 'cursor': '*'}
            entry['error'] = str(exc)
            entry['papers'] = [p for p in entry['papers'] if matches_orcid(p, s['orcid'])]
            print(s['name'], 'FAILED', str(exc), flush=True)
        return s['id'], entry
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        result['scholars'] = dict(pool.map(one, scholars))
    path.parent.mkdir(exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)

if __name__ == '__main__':
    main()
