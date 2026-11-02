"""Build the static gallery with a small index and one catalog per scholar."""
import argparse
import json
import re
import shutil
from pathlib import Path

import collect

ROOT = Path(__file__).resolve().parent
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
PUBLIC_FILES = ('index.html', 'app.js', 'style.css', 'scholars.json',
                'data/catalog.json', 'data/source-report.json')


def read_json(path):
    return json.loads(path.read_text(encoding='utf8'))


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf8')


def matches(paper, orcid):
    if not isinstance(paper, dict) or not isinstance(paper.get('authorDetails'), list):
        return False
    return any(isinstance(author, dict) and isinstance(author.get('authorId'), dict)
               and author['authorId'].get('type') == 'ORCID'
               and author['authorId'].get('value') == orcid
               for author in paper['authorDetails'])


def build_site(source=ROOT, output=None):
    source = Path(source).resolve()
    output = (Path(output) if output is not None else source / '_site').resolve()
    if output == source or output in source.parents:
        raise ValueError('Build output cannot replace the source directory or its parents')
    if source in output.parents:
        first = output.relative_to(source).parts[0]
        if first in {'.git', '.github', 'data', 'assets', 'tests'} or first in PUBLIC_FILES:
            raise ValueError('Build output must be a separate directory from source files')
    if output.exists() and not output.is_dir():
        raise ValueError('Build output must be a directory')

    scholars = read_json(source / 'scholars.json')
    catalog = read_json(source / 'data/catalog.json')
    if not isinstance(scholars, list) or not isinstance(catalog, dict):
        raise ValueError('Invalid scholar configuration or catalog')
    entries = catalog.get('scholars')
    if not isinstance(entries, dict):
        raise ValueError('Catalog must contain scholar entries')
    configured = {}
    for scholar in scholars:
        sid = scholar.get('id') if isinstance(scholar, dict) else None
        if not isinstance(sid, str) or not SLUG.fullmatch(sid):
            raise ValueError('Invalid scholar id; only lowercase slugs are allowed')
        if sid in configured:
            raise ValueError('Duplicate scholar id: ' + sid)
        collect.orcid_query(scholar.get('orcid'))
        configured[sid] = scholar['orcid']
    if not configured or set(entries) != set(configured):
        raise ValueError('Configured scholars and catalog entries must match exactly')

    # Validate everything before writing a publishable output directory.
    index = {key: value for key, value in catalog.items() if key != 'scholars'}
    index['scholars'] = {}
    shards = {}
    for sid, orcid in configured.items():
        entry = entries[sid]
        if not isinstance(entry, dict) or not isinstance(entry.get('papers'), list):
            raise ValueError('Invalid scholar entry: ' + sid)
        if entry.get('orcid') != orcid:
            raise ValueError('Catalog scholar ORCID does not match configuration: ' + sid)
        for paper in entry['papers']:
            if not matches(paper, orcid):
                raise ValueError('Paper is missing the configured author ORCID: ' + sid)
        shards[sid] = json_bytes(entry)
        index['scholars'][sid] = {
            **{key: value for key, value in entry.items() if key != 'papers'},
            'paperCount': len(entry['papers']),
            'file': 'data/scholars/' + sid + '.json',
        }
    public = [source / relative for relative in PUBLIC_FILES]
    for path in public:
        if not path.is_file() or path.is_symlink() or source not in path.resolve().parents:
            raise ValueError('Missing or unsafe public source file: ' + str(path))
    assets = source / 'assets'
    if assets.exists():
        if not assets.is_dir() or assets.is_symlink():
            raise ValueError('Assets must be a regular source directory')
        if any(path.is_symlink() for path in assets.rglob('*')):
            raise ValueError('Asset symlinks cannot be published')

    (output / 'data/scholars').mkdir(parents=True, exist_ok=True)
    for path in public:
        destination = output / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    if assets.exists():
        shutil.copytree(assets, output / 'assets', dirs_exist_ok=True)
    for sid, payload in shards.items():
        (output / 'data/scholars' / (sid + '.json')).write_bytes(payload)
    payload = json_bytes(index)
    (output / 'data/catalog-index.json').write_bytes(payload)
    return {'output': str(output), 'scholars': len(shards), 'indexBytes': len(payload),
            'shardBytes': {sid: len(value) for sid, value in shards.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '_site')
    args = parser.parse_args()
    print(json.dumps(build_site(output=args.output), ensure_ascii=True))


if __name__ == '__main__':
    main()
