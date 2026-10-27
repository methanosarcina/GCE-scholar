"""Automatic DOI-matched illustrations from publisher RSS and PMC Cloud datasets.

Uses public HTTP APIs only. No browser, saved session, CAPTCHA handling, or
per-article page snapshots. Never adds papers to the fixed-ORCID catalog.
"""
import argparse
import collections
import concurrent.futures
import datetime
import json
import hashlib
import re
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup
from collect import ROOT, matches_orcid
from enrich import canonical, save_json
from publisher import LABEL, clean_source, https_url, verify_image

S3 = 'https://pmc-oa-opendata.s3.amazonaws.com/'
AGENT = 'ScholarGallery/2.0 (public DOI-matched illustration retrieval)'
RANK = {'摘要图': 0, '期刊目录图': 1, '课题组配图': 2, '正文插图': 3}
XLINK = '{http://www.w3.org/1999/xlink}href'
REQUEST_LOCK = threading.Lock()
NEXT_REQUEST = {}
COOLDOWN = {}


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def get_bytes(url, limit=4_000_000):
    host = urllib.parse.urlsplit(url).hostname
    with REQUEST_LOCK:
        current = time.monotonic()
        if COOLDOWN.get(host, 0) > current:
            raise RuntimeError('Source is cooling down after an HTTP 429 response')
        scheduled = max(current, NEXT_REQUEST.get(host, 0))
        NEXT_REQUEST[host] = scheduled + (1.25 if host == 'api.crossref.org' else 0.3)
    time.sleep(max(0, scheduled - time.monotonic()))
    request = urllib.request.Request(url, headers={'User-Agent': AGENT})
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            content = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            try:
                delay = max(30, float(exc.headers.get('Retry-After', '60')))
            except ValueError:
                delay = 60
            with REQUEST_LOCK:
                COOLDOWN[host] = time.monotonic() + delay
        raise
    if len(content) > limit:
        raise ValueError('Public metadata response exceeds size limit')
    return content


def get_json(url):
    return json.loads(get_bytes(url))


def local_name(node):
    return node.tag.rsplit('}', 1)[-1]


def journal_key(value):
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower().removeprefix('the '))


def parse_feed(content, feed_url):
    """RSS article images remain catalog images unless explicitly labeled GA."""
    root = ET.fromstring(content)
    found = {}
    for item in root.iter():
        if local_name(item) not in ('item', 'entry'):
            continue
        children = list(item)
        ids = {canonical(n.text) for n in children
               if local_name(n) in ('doi', 'identifier') and canonical(n.text)}
        links = [n.get('href') or n.text or '' for n in children if local_name(n) == 'link']
        if not ids:
            ids = {canonical(link) for link in links if canonical(link)}
        if len(ids) != 1:
            continue
        doi = ids.pop()
        source = next((https_url(link, feed_url) for link in links
                       if https_url(link, feed_url)), None)
        if not source:
            continue
        description = next((n.text or '' for n in children
                            if local_name(n) in ('description', 'encoded', 'content')), '')
        soup = BeautifulSoup(description, 'html.parser')
        for image in soup.find_all('img'):
            url = https_url(image.get('src') or image.get('data-src'), source)
            if not url or re.search(r'(?:^|[/_-])(logo|cover|masthead|portrait)(?:[._/-]|$)', url, re.I):
                continue
            label = image.get('alt', '').strip()
            explicit = bool(LABEL.fullmatch(label))
            found[doi] = {
                'url': url, 'kind': '摘要图' if explicit else '期刊目录图',
                'provider': 'publisher-rss', 'source': clean_source(source),
                'feedSource': feed_url, 'doi': doi, 'match': 'exact-doi',
                'evidence': 'Explicit abstract label in RSS' if explicit else 'Publisher-designated RSS article image',
                'caption': '出版社官方 RSS 为该 DOI 提供的期刊配图。',
            }
            break
    return found


def registered_feeds(record):
    if record.get('feeds'):
        return [url for url in record['feeds'] if https_url(url, '') == url]
    code = record.get('code', '')
    if not re.fullmatch(r'[a-z0-9]{4,12}', code):
        return []
    return [f'https://pubs.acs.org/rss/{code}/asap.xml',
            f'https://pubs.acs.org/rss/{code}/currentIssue.xml']


def discover_acs_journal(paper):
    """Crossref supplies the current journal path after publisher migrations."""
    doi = canonical(paper.get('doi'))
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='')
    record = get_json(url)['message']
    if canonical(record.get('DOI')) != doi:
        raise ValueError('Crossref DOI mismatch')
    primary = record.get('resource', {}).get('primary', {}).get('URL', '')
    parsed = urllib.parse.urlsplit(primary)
    parts = parsed.path.strip('/').split('/')
    code = parts[0] if parts else ''
    if parsed.hostname != 'pubs.acs.org' or not re.fullmatch(r'[a-z0-9]{4,12}', code) or code == 'doi':
        return {'status': 'no_current_journal_path', 'metadataSource': url}
    # Feed routes are published at https://pubs.acs.org/pages/rss.
    return {
        'status': 'ok', 'code': code, 'journal': paper.get('journal', ''),
        'metadataSource': url, 'primaryURL': primary,
        'feeds': [f'https://pubs.acs.org/rss/{code}/asap.xml',
                  f'https://pubs.acs.org/rss/{code}/currentIssue.xml'],
    }


def parse_s3_listing(content, pmcid):
    root = ET.fromstring(content)
    keys = [n.text for n in root.iter() if local_name(n) == 'Key']
    pattern = re.compile(re.escape(pmcid) + r'\.(\d+)/' + re.escape(pmcid) + r'\.\1\.json')
    return [key for key in keys if key and pattern.fullmatch(key)]


def s3_url(value):
    parsed = urllib.parse.urlsplit(value or '')
    if parsed.scheme == 's3' and parsed.netloc == 'pmc-oa-opendata':
        return S3 + parsed.path.lstrip('/') + ('?' + parsed.query if parsed.query else '')
    if parsed.scheme == 'https' and parsed.hostname == 'pmc-oa-opendata.s3.amazonaws.com':
        return value
    return None


def parse_jats(content, metadata, expected_doi):
    """Only map explicitly labeled GA to media URLs disclosed by PMC metadata."""
    if canonical(metadata.get('doi')) != expected_doi:
        return [], 'doi_mismatch'
    root = ET.fromstring(content)
    ids = {canonical(n.text) for meta in root.iter() if local_name(meta) == 'article-meta'
           for n in list(meta) if local_name(n) == 'article-id'
           and n.get('pub-id-type') == 'doi' and canonical(n.text)}
    if ids != {expected_doi}:
        return [], 'doi_mismatch'
    media = {}
    for item in metadata.get('media_urls') or []:
        url = s3_url(item if isinstance(item, str) else item.get('url'))
        if url:
            filename = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1])
            if re.search(r'\.(png|jpg|jpeg|gif|webp)$', filename, re.I):
                media[filename] = url
    candidates = []
    detected = False
    for node in root.iter():
        tag = local_name(node)
        title = ' '.join(' '.join(c.itertext()) for c in list(node)
                         if local_name(c) in ('title', 'label'))
        marker = node.get('abstract-type', '') + ' ' + node.get('fig-type', '') + ' ' + title
        if tag not in ('abstract', 'fig') or not (
            LABEL.search(marker) or node.get('abstract-type') in ('graphical', 'toc')
            or node.get('fig-type') in ('graphical', 'toc')):
            continue
        detected = True
        for graphic in node.iter():
            if local_name(graphic) != 'graphic':
                continue
            href = graphic.get(XLINK, '')
            filename = urllib.parse.unquote(urllib.parse.urlsplit(href).path.rsplit('/', 1)[-1])
            matches = [url for name, url in media.items() if name == filename]
            if not matches:
                stem = filename.rsplit('.', 1)[0]
                matches = [url for name, url in media.items() if name.rsplit('.', 1)[0] == stem]
            for url in matches[:1]:
                candidates.append({
                    'url': url, 'kind': '摘要图', 'provider': 'pmc-cloud',
                    'source': 'https://pmc.ncbi.nlm.nih.gov/articles/' + metadata['pmcid'] + '/',
                    'doi': expected_doi, 'pmcid': metadata['pmcid'], 'match': 'exact-doi-and-pmcid',
                    'evidence': 'JATS explicitly labeled graphical abstract with disclosed media URL',
                    'license': metadata.get('license_code', ''),
                    'datasetVersion': metadata.get('version'),
                    'caption': 'PMC / 美国国家医学图书馆（NLM）开放数据中的图形摘要。',
                })
    if candidates:
        return candidates, 'found_candidates'
    if detected:
        return [], 'abstract_media_unavailable'
    if not media:
        return [], 'no_repository_media'
    return [], 'no_graphic_detected'


def inspect_pmc(paper):
    pmcid = paper.get('pmcid', '')
    doi = canonical(paper.get('doi'))
    if not re.fullmatch(r'PMC\d+', pmcid):
        return None, 'no_pmcid'
    listing_url = S3 + '?' + urllib.parse.urlencode({
        'list-type': '2', 'prefix': pmcid + '.', 'max-keys': 1000})
    keys = parse_s3_listing(get_bytes(listing_url), pmcid)
    keys.sort(key=lambda key: int(key.split('/')[0].rsplit('.', 1)[-1]), reverse=True)
    if not keys:
        return None, 'no_repository_version'
    checked = []
    for key in keys[:4]:
        metadata = get_json(S3 + urllib.parse.quote(key, safe='/'))
        if metadata.get('pmcid') != pmcid or canonical(metadata.get('doi')) != doi:
            checked.append('doi_mismatch')
            continue
        if metadata.get('is_retracted'):
            return None, 'retracted'
        if not metadata.get('media_urls'):
            checked.append('no_repository_media')
            continue
        xml_url = s3_url(metadata.get('xml_url'))
        if not xml_url:
            checked.append('no_repository_xml')
            continue
        figures, status = parse_jats(get_bytes(xml_url, 8_000_000), metadata, doi)
        checked.append(status)
        for figure in figures:
            try:
                return verify_image(figure, force_cache=True), 'found'
            except Exception as exc:
                checked.append('image_unavailable: ' + str(exc)[:120])
    return None, checked[-1] if checked else 'no_graphic_detected'


def valid_cached(figure):
    url = figure.get('url', '')
    if not re.fullmatch(r'assets/publisher/[a-f0-9]{32}\.(png|jpg|gif|webp)', url):
        return False
    path = ROOT / url
    return path.is_file() and (not figure.get('sha256') or hashlib.sha256(path.read_bytes()).hexdigest() == figure['sha256'])


def due(attempt):
    try:
        return now() >= datetime.datetime.fromisoformat(attempt.get('retryAfter', ''))
    except (ValueError, TypeError):
        return True


def retry_date(status):
    days = 30 if status in ('no_graphic_detected', 'no_repository_media') else 3
    return (now() + datetime.timedelta(days=days)).isoformat()


def apply_figures(catalog, bydoi, figures):
    for doi, papers in bydoi.items():
        choices = [p['figure'] for p in papers if p.get('figure')]
        candidate = figures.get(doi)
        if candidate and valid_cached(candidate):
            choices.append(candidate)
        if not choices:
            continue
        best = min(choices, key=lambda fig: RANK.get(fig.get('kind'), 9))
        for paper in papers:
            if paper.get('figure') != best:
                if paper.get('figure'):
                    paper['fallbackFigure'] = paper['figure']
                paper['figure'] = best
    for entry in catalog['scholars'].values():
        entry['imageCount'] = sum(bool(p.get('figure')) for p in entry['papers'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository-limit', type=int, default=150, help='Maximum previously unverified PMC papers per run')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--max-seconds', type=int, default=900)
    parser.add_argument('--rss-only', action='store_true')
    parser.add_argument('--repository-only', action='store_true', help='Inspect repository media without fetching publisher feeds')
    parser.add_argument('--apply-only', action='store_true')
    parser.add_argument('--retry', action='store_true', help='Ignore retry dates for repository checks')
    args = parser.parse_args()
    started = time.monotonic()
    catalog = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf8'))
    scholars = json.loads((ROOT / 'scholars.json').read_text(encoding='utf8'))
    cache_path = ROOT / 'data/automatic-graphics.json'
    cache = json.loads(cache_path.read_text(encoding='utf8')) if cache_path.exists() else {}
    for key in ('figures', 'attempts', 'rssAttempts', 'journals', 'feeds'):
        cache.setdefault(key, {})
    bydoi = collections.defaultdict(list)
    for scholar in scholars:
        for paper in catalog['scholars'][scholar['id']]['papers']:
            if not matches_orcid(paper, scholar['orcid']):
                raise ValueError('Catalog ORCID integrity failure')
            doi = canonical(paper.get('doi'))
            if doi:
                bydoi[doi].append(paper)
    unique = {p['id']: p for entry in catalog['scholars'].values() for p in entry['papers']}
    previous = {key: (p.get('figure') or {}).get('kind') for key, p in unique.items()}
    stamp = now().isoformat()
    stats = collections.Counter()
    if not args.apply_only:
        registry = json.loads((ROOT / 'publisher-feeds.json').read_text(encoding='utf8'))
        registry_keys = {journal_key(record['journal']) for record in registry['journals']}
        groups = {}
        for papers in bydoi.values():
            paper = papers[0]
            if canonical(paper.get('doi')).startswith('10.1021/') or journal_key(paper.get('journal')) in registry_keys:
                groups.setdefault(journal_key(paper.get('journal')), paper)
        if args.repository_only:
            groups = {}
        for record in registry['journals']:
            key, code = journal_key(record['journal']), record.get('code', '')
            if key in groups:
                cache['journals'][key] = {
                    'status': 'ok', 'code': code, 'journal': record['journal'],
                    'registrySource': registry['source'], 'checkedAt': stamp,
                    'feeds': registered_feeds(record)}
        unresolved = [(key, paper) for key, paper in groups.items()
                      if not cache['journals'].get(key, {}).get('feeds')
                      and (args.retry or due({'retryAfter': cache['journals'].get(key, {}).get('retryAfter', '')}))]
        def discover(pair):
            key, paper = pair
            try:
                result = discover_acs_journal(paper)
            except Exception as exc:
                result = {'status': 'metadata_unavailable', 'detail': str(exc)[:180]}
            return key, {**result, 'checkedAt': stamp, 'retryAfter': retry_date(result.get('status'))}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for key, record in pool.map(discover, unresolved):
                cache['journals'][key] = record
        feeds = sorted({url for key in groups for url in cache['journals'].get(key, {}).get('feeds', [])})
        print('Official publisher feeds:', len(feeds), flush=True)
        def read_feed(url):
            try:
                return url, parse_feed(get_bytes(url), url), 'ok'
            except Exception as exc:
                return url, {}, str(exc)[:160]
        rss_figures = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for url, records, status in pool.map(read_feed, feeds):
                cache['feeds'][url] = {'checkedAt': stamp, 'status': status, 'entries': len(records)}
                stats['feedsRead' if status == 'ok' else 'feedsUnavailable'] += 1
                for doi, figure in records.items():
                    if doi in bydoi:
                        rss_figures.setdefault(doi, figure)
        stats['rssMatches'] = len(rss_figures)
        print('RSS exact DOI matches:', len(rss_figures), flush=True)
        for doi, figure in rss_figures.items():
            old = cache['figures'].get(doi)
            if old and valid_cached(old):
                stats['cachedImages'] += 1
                continue
            try:
                stored = verify_image(figure, force_cache=True)
                cache['figures'][doi] = {**stored, 'checkedAt': stamp}
                stats['rssImages'] += 1
            except Exception as exc:
                cache['rssAttempts'][doi] = {
                    'status': 'rss_image_unavailable', 'detail': str(exc)[:160],
                    'checkedAt': stamp, 'retryAfter': retry_date('image_unavailable')}
        save_json(cache_path, cache)
        candidates = []
        if not args.rss_only:
            for doi, papers in bydoi.items():
                paper = papers[0]
                current = [p.get('figure') or {} for p in papers] + [cache['figures'].get(doi, {})]
                if not paper.get('pmcid') or any(f.get('kind') == '摘要图' for f in current):
                    continue
                if args.retry or due(cache['attempts'].get(doi, {})):
                    candidates.append(paper)
        candidates.sort(key=lambda p: (
            not bool(p.get('oa')),
            bool(p.get('figure')),
            -(int(re.sub(r'\D', '', (p.get('publicationDate') or p.get('year') or '0')).ljust(8, '0')[:8]) or 0)))
        candidates = candidates[:max(0, args.repository_limit)]
        print('PMC Cloud articles to inspect:', len(candidates), flush=True)
        def inspect_one(paper):
            if time.monotonic() - started >= args.max_seconds:
                return paper, None, 'budget_deferred'
            try:
                figure, status = inspect_pmc(paper)
                return paper, figure, status
            except Exception as exc:
                return paper, None, 'request_failed: ' + str(exc)[:150]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for index, (paper, figure, status) in enumerate(pool.map(inspect_one, candidates), 1):
                doi = canonical(paper['doi'])
                cache['attempts'][doi] = {
                    'status': status, 'checkedAt': stamp,
                    'retryAfter': stamp if status == 'budget_deferred' else retry_date(status)}
                stats[status.split(':', 1)[0]] += 1
                if figure:
                    cache['figures'][doi] = {**figure, 'checkedAt': stamp}
                    stats['repositoryImages'] += 1
                if index % 25 == 0:
                    save_json(cache_path, cache)
                    print('PMC checked:', index, '/', len(candidates), dict(stats), flush=True)
    apply_figures(catalog, bydoi, cache['figures'])
    summary = {
        'updated': stamp, 'cachedFigures': len(cache['figures']), 'run': dict(stats),
        'addedImages': sum(not previous[key] and bool(p.get('figure')) for key, p in unique.items()),
        'upgradedToAbstract': sum(previous[key] != '摘要图' and (p.get('figure') or {}).get('kind') == '摘要图'
                                 for key, p in unique.items()),
        'providers': dict(collections.Counter(fig.get('provider') for fig in cache['figures'].values())),
        'policy': 'Only exact DOI matches in the fixed-ORCID catalog; no UI or browser sessions',
    }
    cache['summary'] = summary
    catalog['automaticGraphicsAt'] = stamp
    report_path = ROOT / 'data/source-report.json'
    report = json.loads(report_path.read_text(encoding='utf8'))
    report['automaticGraphics'] = summary
    report['summary']['withImages'] = sum(bool(p.get('figure')) for p in unique.values())
    report['summary']['abstractGraphics'] = sum((p.get('figure') or {}).get('kind') == '摘要图' for p in unique.values())
    report['summary']['catalogGraphics'] = sum((p.get('figure') or {}).get('kind') == '期刊目录图' for p in unique.values())
    save_json(cache_path, cache)
    save_json(ROOT / 'data/catalog.json', catalog)
    save_json(report_path, report)
    print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
