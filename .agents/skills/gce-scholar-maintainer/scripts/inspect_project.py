"""Read-only checks and compact counts for a fixed-ORCID Scholar Gallery."""
import argparse
import collections
import json
import re
from pathlib import Path


SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
ORCID = re.compile(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]')
LOCAL_IMAGE = re.compile(r'assets/publisher/[a-f0-9]{32}\.(?:png|jpg|gif|webp)')
REQUIRED = ('scholars.json', 'collect.py', 'build.py')


def find_root(explicit=None):
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        if all((candidate / name).is_file() for name in REQUIRED):
            return candidate
        raise ValueError('The requested root is missing scholars.json, collect.py, or build.py')
    starts = (Path.cwd().resolve(), Path(__file__).resolve().parent)
    seen = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate not in seen and all((candidate / name).is_file() for name in REQUIRED):
                return candidate
            seen.add(candidate)
    raise ValueError('Cannot find a Scholar Gallery root; provide --root')


def read_json(path):
    return json.loads(path.read_text(encoding='utf8'))


def exact_author(paper, orcid):
    authors = paper.get('authorDetails') if isinstance(paper, dict) else None
    return isinstance(authors, list) and any(
        isinstance(author, dict) and isinstance(author.get('authorId'), dict)
        and author['authorId'].get('type') == 'ORCID'
        and author['authorId'].get('value') == orcid for author in authors)


def inspect(root, selected=None, recent=0):
    issues = []
    config = read_json(root / 'scholars.json')
    catalog = read_json(root / 'data/catalog.json')
    report_path = root / 'data/source-report.json'
    report = read_json(report_path) if report_path.is_file() else {}
    if not isinstance(config, list) or not isinstance(catalog, dict):
        raise ValueError('Scholar configuration must be a list and catalog must be an object')
    entries = catalog.get('scholars')
    if not isinstance(entries, dict):
        raise ValueError('Catalog must contain a scholars object')
    if not isinstance(report, dict):
        raise ValueError('Source report must be an object when present')

    scholars, orcids = {}, set()
    orcid_ok = True
    for index, scholar in enumerate(config):
        if not isinstance(scholar, dict):
            issues.append('Configuration row ' + str(index) + ' is not an object')
            orcid_ok = False
            continue
        sid, orcid = scholar.get('id'), scholar.get('orcid')
        if not isinstance(sid, str) or not SLUG.fullmatch(sid):
            issues.append('Configuration row ' + str(index) + ' has an unsafe scholar id')
            continue
        if sid in scholars:
            issues.append('Duplicate scholar id: ' + sid)
            continue
        scholars[sid] = scholar
        if not isinstance(orcid, str) or not ORCID.fullmatch(orcid):
            issues.append('Invalid fixed ORCID: ' + sid)
            orcid_ok = False
        elif orcid in orcids:
            issues.append('Fixed ORCID is shared by multiple configured scholars: ' + sid)
            orcid_ok = False
        else:
            orcids.add(orcid)

    configured, present = set(scholars), set(entries)
    config_only, catalog_only = sorted(configured - present), sorted(present - configured)
    if config_only or catalog_only:
        issues.append('Configuration and catalog membership differ')
    for sid in present:
        if not isinstance(sid, str) or not SLUG.fullmatch(sid):
            issues.append('Catalog contains an unsafe scholar id')
    selected = set(selected) if selected else configured
    for sid in sorted(selected - configured):
        issues.append('Unknown selected scholar: ' + sid)

    unique_dois, epmc_dois = set(), set()
    crossref_owners, all_owners = collections.defaultdict(set), collections.defaultdict(set)
    crossref_records = 0
    summaries = []
    for sid, scholar in scholars.items():
        if sid not in entries:
            continue
        entry = entries[sid]
        if not isinstance(entry, dict) or not isinstance(entry.get('papers'), list):
            issues.append('Invalid catalog entry: ' + sid)
            orcid_ok = False
            continue
        orcid = scholar.get('orcid')
        if entry.get('orcid') != orcid or entry.get('query') != 'AUTHORID:"' + str(orcid) + '"':
            issues.append('Entry ORCID or query differs from its fixed configuration: ' + sid)
            orcid_ok = False
        seen, image_count, crossref_count = set(), 0, 0
        papers = []
        for index, paper in enumerate(entry['papers']):
            if not isinstance(paper, dict):
                issues.append('Invalid paper object: ' + sid + ' row ' + str(index))
                orcid_ok = False
                continue
            papers.append(paper)
            raw_doi = paper.get('doi')
            doi = raw_doi.strip().lower() if isinstance(raw_doi, str) else ''
            label = sid + ': ' + (doi or str(paper.get('id') or 'row ' + str(index)))
            if not exact_author(paper, orcid):
                issues.append('Paper lacks the fixed author ORCID: ' + label)
                orcid_ok = False
            if doi:
                if doi in seen:
                    issues.append('Duplicate DOI within a scholar: ' + label)
                seen.add(doi)
                unique_dois.add(doi)
                all_owners[doi].add(sid)
            is_crossref = paper.get('metadataSource') == 'crossref'
            if is_crossref:
                crossref_count += 1
                crossref_records += 1
                if doi:
                    crossref_owners[doi].add(sid)
            elif doi:
                epmc_dois.add(doi)
            image_count += bool(paper.get('figure'))
            for field in ('figure', 'fallbackFigure'):
                figure = paper.get(field)
                if figure is None:
                    continue
                if not isinstance(figure, dict):
                    issues.append('Invalid ' + field + ' object: ' + label)
                    continue
                url = figure.get('url')
                if isinstance(url, str) and url.startswith(('https://', 'http://')):
                    continue
                if not isinstance(url, str) or not LOCAL_IMAGE.fullmatch(url):
                    issues.append('Unsafe local ' + field + ' path: ' + label)
                elif not (root / url).is_file():
                    issues.append('Missing local ' + field + ' asset: ' + label)
        if sid in selected:
            summary = {'id': sid, 'name': scholar.get('name', sid),
                       'papers': len(entry['papers']), 'images': image_count,
                       'crossrefRecords': crossref_count}
            if recent:
                ordered = sorted(papers, key=lambda paper: (
                    str(paper.get('publicationDate') or paper.get('year') or ''),
                    str(paper.get('doi') or '')), reverse=True)
                summary['recent'] = [
                    {'title': paper.get('title', ''), 'doi': paper.get('doi', ''),
                     'publicationDate': paper.get('publicationDate') or paper.get('year', ''),
                     'metadataSource': paper.get('metadataSource') or 'europepmc'}
                    for paper in ordered[:recent]]
            summaries.append(summary)
    crossref_dois = set(crossref_owners)
    crossref_report = report.get('crossref') or {}
    return {'root': str(root), 'catalogUpdated': catalog.get('updated'),
            'orcidIntegrity': orcid_ok,
            'membership': {'matches': not config_only and not catalog_only,
                           'configOnly': config_only, 'catalogOnly': catalog_only},
            'scholars': summaries,
            'global': {'configuredScholars': len(scholars), 'catalogScholars': len(entries),
                       'uniqueDOIs': len(unique_dois),
                       'crossScholarDuplicateDOIs': sum(len(owners) > 1 for owners in all_owners.values()),
                       'crossref': {'records': crossref_records, 'uniqueDOIs': len(crossref_dois),
                                    'europePMCOverlapDOIs': sorted(crossref_dois & epmc_dois),
                                    'crossScholarDuplicates': [
                                        {'doi': doi, 'scholars': sorted(owners)}
                                        for doi, owners in sorted(crossref_owners.items()) if len(owners) > 1]}},
            'sourceReportUpdated': report.get('updated'),
            'crossrefReportUpdated': crossref_report.get('updated') if isinstance(crossref_report, dict) else None,
            'ok': not issues, 'issueCount': len(issues), 'issues': issues[:20]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--scholar', action='append', help='Only print selected scholar summaries; checks remain global')
    parser.add_argument('--recent', type=int, default=0)
    args = parser.parse_args()
    try:
        if args.recent < 0:
            raise ValueError('--recent must be nonnegative')
        result = inspect(find_root(args.root), args.scholar, args.recent)
    except (ValueError, OSError, TypeError) as exc:
        result = {'ok': False, 'orcidIntegrity': False, 'issues': [str(exc)], 'issueCount': 1}
    # ASCII JSON also preserves scientific characters on Windows terminals with
    # legacy output encodings; JSON readers recover the original Unicode text.
    print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
