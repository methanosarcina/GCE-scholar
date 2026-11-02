"""Supplement the catalog with recent journal articles bearing fixed ORCIDs.

Europe PMC records remain authoritative when the same DOI is already present.
Previously verified Crossref-only papers survive the rolling query window and
temporary API failures. Neither names nor affiliations grant admission.
"""
import argparse
import copy
import datetime
import json
import re
import time
import urllib.parse
from pathlib import Path

import collect

ROOT = Path(__file__).resolve().parent
API = 'https://api.crossref.org/works'
FIELDS = ('DOI,title,abstract,container-title,published,published-online,'
          'published-print,author,is-referenced-by-count,type,URL')
ROWS = 200
DECORATIONS = ('figure', 'fallbackFigure', 'labSources')


def canonical_doi(value):
    """Accept an entire DOI, never a substring of an arbitrary URL or script."""
    if not isinstance(value, str):
        return ''
    value = value.strip().lower()
    if (not re.fullmatch(r'10\.\d{4,9}/[-._;()/:a-z0-9]+', value)
            or len(value) > 1000 or any(part in ('.', '..') for part in value.split('/'))):
        return ''
    return value


def canonical_orcid(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dXx]', value):
        return value.upper()
    try:
        parsed = urllib.parse.urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or parsed.hostname != 'orcid.org'
                or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.query or parsed.fragment):
            return ''
        if re.fullmatch(r'/\d{4}-\d{4}-\d{4}-\d{3}[\dXx]', parsed.path):
            return parsed.path[1:].upper()
    except ValueError:
        pass
    return ''


def clean(value):
    return re.sub(r'\s+', ' ', collect.plain(value if isinstance(value, str) else ''))


def parts_date(value):
    parts = value.get('date-parts') if isinstance(value, dict) else None
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return ''
    parts = parts[0]
    if not 1 <= len(parts) <= 3 or any(type(number) is not int for number in parts):
        return ''
    raw = '-'.join(f'{number:04d}' if i == 0 else f'{number:02d}'
                   for i, number in enumerate(parts))
    return collect.publication_date(raw)


def dates(work):
    online = parts_date(work.get('published-online'))
    printed = parts_date(work.get('published-print'))
    published = parts_date(work.get('published'))
    selected = online or printed or published
    return dict(publicationDate=selected,
                datePrecision={4: 'year', 7: 'month', 10: 'day'}.get(len(selected), ''),
                dateSource='online' if online else ('print' if printed else ('published' if published else '')),
                onlinePublicationDate=online, printPublicationDate=printed)


def normalize(work, orcid):
    if not isinstance(work, dict) or work.get('type') != 'journal-article':
        return None
    doi = canonical_doi(work.get('DOI'))
    if not doi:
        return None
    authors = []
    for author in work.get('author') or []:
        if not isinstance(author, dict):
            continue
        first, last = clean(author.get('given')), clean(author.get('family'))
        detail = dict(firstName=first, lastName=last,
                      fullName=' '.join(part for part in (first, last) if part) or clean(author.get('name')))
        author_orcid = canonical_orcid(author.get('ORCID'))
        if author_orcid:
            detail['authorId'] = {'type': 'ORCID', 'value': author_orcid}
        authors.append(detail)
    if not collect.matches_orcid({'authorDetails': authors}, orcid):
        return None
    publication = dates(work)
    title = work.get('title') or []
    journal = work.get('container-title') or []
    try:
        citations = max(0, int(work.get('is-referenced-by-count', 0)))
    except (ValueError, TypeError):
        citations = 0
    return dict(id='DOI:' + doi, doi=doi,
                title=clean(title[0] if isinstance(title, list) and title else ''),
                journal=clean(journal[0] if isinstance(journal, list) and journal else ''),
                abstract=clean(work.get('abstract')),
                authors=', '.join(author['fullName'] for author in authors if author['fullName']),
                authorDetails=authors, year=publication['publicationDate'][:4],
                oa=False, pmcid='', license='', citations=citations,
                url='https://doi.org/' + urllib.parse.quote(doi, safe='/'),
                metadataSource='crossref', metadataURL=API + '/' + urllib.parse.quote(doi, safe='/'),
                source='Crossref', type='journal-article', **publication)


def fetch_works(orcid, from_date):
    collect.orcid_query(orcid)
    cursor, seen = '*', set()
    papers = {}
    while True:
        query = urllib.parse.urlencode({'filter': f'orcid:{orcid},from-pub-date:{from_date}',
                                       'cursor': cursor, 'rows': ROWS, 'select': FIELDS})
        payload = json.loads(collect.fetch(API + '?' + query))
        message = payload.get('message', {})
        items = message.get('items')
        if not isinstance(items, list):
            raise ValueError('Crossref response did not contain an article list')
        for work in items:
            paper = normalize(work, orcid)
            if paper:
                papers[paper['doi']] = paper
        # Crossref documents a short page as the end of cursor pagination.
        next_cursor = message.get('next-cursor')
        if len(items) < ROWS or not next_cursor:
            break
        seen.add(cursor)
        if not isinstance(next_cursor, str) or next_cursor in seen:
            raise ValueError('Crossref repeated a pagination cursor; cached results retained')
        cursor = next_cursor
        time.sleep(1.1)
    return list(papers.values())


def safe_cached(papers, orcid):
    result = {}
    for paper in papers if isinstance(papers, list) else []:
        if not isinstance(paper, dict) or paper.get('metadataSource') != 'crossref' or paper.get('type') != 'journal-article':
            continue
        doi = canonical_doi(paper.get('doi'))
        authors = paper.get('authorDetails')
        if (not doi or not isinstance(authors, list)
                or not all(isinstance(author, dict) and isinstance(author.get('authorId', {}), dict) for author in authors)
                or not collect.matches_orcid(paper, orcid)):
            continue
        paper = copy.deepcopy(paper)
        paper.update(id='DOI:' + doi, doi=doi, source='Crossref',
                     url='https://doi.org/' + urllib.parse.quote(doi, safe='/'),
                     metadataURL=API + '/' + urllib.parse.quote(doi, safe='/'))
        result[doi] = paper
    return result


def preserve_images(paper, previous):
    for key in DECORATIONS:
        if previous.get(key):
            paper[key] = copy.deepcopy(previous[key])


def supplement(catalog, scholars, cache, *, selected=None, days=365, apply_only=False,
               today=None, now=None):
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    now = now or datetime.datetime.now(datetime.timezone.utc).isoformat()
    from_date = (today - datetime.timedelta(days=days)).isoformat()
    ids = {scholar['id'] for scholar in scholars}
    selected = ids if selected is None else set(selected)
    if not selected <= ids:
        raise ValueError('Unknown scholar: ' + ', '.join(sorted(selected - ids)))
    old_cache = cache.get('scholars', {})
    refreshed = {'version': 1, 'updated': now, 'scholars': {}}
    report = dict(updated=now, windowDays=days, fromDate=from_date,
                  policy='Journal articles with an exact fixed author ORCID only; existing Europe PMC records preserved.',
                  scholars=[])
    requests = 0
    for scholar in scholars:
        sid, orcid = scholar['id'], scholar['orcid']
        collect.orcid_query(orcid)
        old = old_cache.get(sid, {})
        if old.get('orcid') != orcid:
            old = {}
        cached = safe_cached(old.get('papers'), orcid)
        entry = catalog['scholars'].get(sid)
        if entry is None:
            # Do not fabricate Europe PMC completeness or totals.
            raise ValueError('Scholar is missing from the base catalog: ' + sid)
        current = {canonical_doi(paper.get('doi')): paper for paper in entry.get('papers', [])
                   if canonical_doi(paper.get('doi')) and collect.matches_orcid(paper, orcid)}
        for doi, paper in cached.items():
            preserve_images(paper, current.get(doi, {}))
        record = {key: copy.deepcopy(value) for key, value in old.items() if key != 'papers'}
        record.update(orcid=orcid)
        status, error = 'cached-only', ''
        if sid in selected and not apply_only:
            if requests:
                time.sleep(1.1)
            requests += 1
            record.update(lastAttempt=now, fromDate=from_date)
            try:
                for paper in fetch_works(orcid, from_date):
                    previous = cached.get(paper['doi'], {})
                    preserve_images(paper, previous)
                    preserve_images(paper, current.get(paper['doi'], {}))
                    cached[paper['doi']] = paper
                record.update(lastSuccess=now, status='ok')
                record.pop('error', None)
                status = 'ok'
            except Exception as exc:
                error = str(exc)
                status = 'unavailable'
                record.update(status=status, error=error)
        # Revalidate after merging; cached identities cannot grant name matches.
        cached = safe_cached(list(cached.values()), orcid)
        record['papers'] = list(cached.values())
        refreshed['scholars'][sid] = record
        existing_dois = {canonical_doi(paper.get('doi')) for paper in entry.get('papers', [])}
        added = 0
        for doi, paper in cached.items():
            if doi not in existing_dois:
                entry.setdefault('papers', []).append(copy.deepcopy(paper))
                existing_dois.add(doi)
                added += 1
        entry['crossrefCount'] = sum(paper.get('metadataSource') == 'crossref' for paper in entry['papers'])
        entry['crossrefUpdated'] = record.get('lastSuccess', '')
        entry['imageCount'] = sum(bool(paper.get('figure')) for paper in entry['papers'])
        item = dict(id=sid, orcid=orcid, status=status, cached=len(cached), added=added,
                    lastSuccess=record.get('lastSuccess', ''))
        if error:
            item['error'] = error
        report['scholars'].append(item)
        print(scholar.get('name', sid), 'Crossref', status, 'cached', len(cached), 'added', added, flush=True)
    report['summary'] = dict(successfulQueries=sum(item['status'] == 'ok' for item in report['scholars']),
                             failedQueries=sum(item['status'] == 'unavailable' for item in report['scholars']),
                             cachedPapers=sum(item['cached'] for item in report['scholars']),
                             addedPapers=sum(item['added'] for item in report['scholars']))
    catalog['crossrefUpdated'] = now
    return refreshed, report


def positive_days(value):
    try:
        days = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('days must be a positive integer')
    if days <= 0:
        raise argparse.ArgumentTypeError('days must be a positive integer')
    return days


def read_json(path, fallback):
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else fallback


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scholar', action='append', help='Scholar id to query; repeat to select several (default: all)')
    parser.add_argument('--days', type=positive_days, default=365)
    parser.add_argument('--apply-only', action='store_true', help='Restore previously verified cache without network requests')
    args = parser.parse_args()
    catalog_path = ROOT / 'data/catalog.json'
    cache_path = ROOT / 'data/crossref.json'
    report_path = ROOT / 'data/source-report.json'
    scholars = read_json(ROOT / 'scholars.json', [])
    catalog = read_json(catalog_path, {'scholars': {}})
    cache, report = supplement(catalog, scholars, read_json(cache_path, {}),
                               selected=args.scholar, days=args.days, apply_only=args.apply_only)
    source_report = read_json(report_path, {})
    source_report['crossref'] = report
    save_json(cache_path, cache)
    save_json(catalog_path, catalog)
    save_json(report_path, source_report)
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
