import json
import tempfile
import unittest
from pathlib import Path

import build


class StaticBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / 'source'
        self.source.mkdir()
        self.output = self.source / '_site'
        self.orcid = '0000-0001-7602-5050'
        self.paper = {'id': 'DOI:10.1021/example', 'doi': '10.1021/example',
                      'title': 'A paper 图', 'abstract': 'The full abstract.',
                      'authorDetails': [{'firstName': 'Jie', 'lastName': 'Wang',
                                         'authorId': {'type': 'ORCID', 'value': self.orcid}}],
                      'figure': {'url': 'assets/publisher/example.png'}}
        self.scholars = [{'id': 'jie-wang', 'name': 'Jie Wang', 'orcid': self.orcid}]
        self.catalog = {'updated': '2026-11-02', 'crossrefUpdated': '2026-11-02T12:00:00Z',
                        'scholars': {'jie-wang': {'papers': [self.paper], 'total': 4,
                                                 'complete': True, 'orcid': self.orcid,
                                                 'query': 'AUTHORID:"' + self.orcid + '"',
                                                 'labSource': {'url': 'https://faculty.example/'}}}}
        self.write_json('scholars.json', self.scholars)
        self.write_json('data/catalog.json', self.catalog)
        self.write_json('data/source-report.json', {'crossref': {'addedPapers': 1}})
        for name in ('index.html', 'app.js', 'style.css'):
            (self.source / name).write_text(name, encoding='utf8')
        image = self.source / 'assets/publisher/example.png'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'original-image-bytes')

    def write_json(self, name, value):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')

    def test_shards_keep_all_paper_data_and_index_keeps_only_entry_metadata(self):
        original = (self.source / 'data/catalog.json').read_bytes()
        stats = build.build_site(self.source, self.output)
        index = json.loads((self.output / 'data/catalog-index.json').read_text(encoding='utf8'))
        metadata = index['scholars']['jie-wang']
        self.assertNotIn('papers', metadata)
        self.assertEqual(metadata['paperCount'], 1)
        self.assertEqual(metadata['total'], 4)
        self.assertEqual(metadata['labSource'], self.catalog['scholars']['jie-wang']['labSource'])
        self.assertEqual(index['crossrefUpdated'], self.catalog['crossrefUpdated'])
        shard = self.output / metadata['file']
        self.assertEqual(json.loads(shard.read_text(encoding='utf8')), self.catalog['scholars']['jie-wang'])
        self.assertEqual(stats['shardBytes']['jie-wang'], shard.stat().st_size)
        self.assertNotIn(b'\n', shard.read_bytes())
        self.assertEqual((self.output / 'data/catalog.json').read_bytes(), original)
        self.assertEqual((self.source / 'data/catalog.json').read_bytes(), original)

    def test_public_files_and_assets_are_copied_unchanged_and_rebuild_is_supported(self):
        build.build_site(self.source, self.output)
        for name in build.PUBLIC_FILES + ('assets/publisher/example.png',):
            self.assertEqual((self.source / name).read_bytes(), (self.output / name).read_bytes())
        (self.source / 'app.js').write_text('new version', encoding='utf8')
        build.build_site(self.source, self.output)
        self.assertEqual((self.output / 'app.js').read_text(encoding='utf8'), 'new version')

    def test_wrong_or_missing_author_orcid_blocks_publication_before_output_is_written(self):
        for authors in ([], [{'authorId': {'type': 'ORCID', 'value': '0000-0001-9808-6890'}}],
                        [{'fullName': 'Jie Wang'}], [{'authorId': None}]):
            with self.subTest(authors=authors):
                self.paper['authorDetails'] = authors
                self.write_json('data/catalog.json', self.catalog)
                with self.assertRaisesRegex(ValueError, 'configured author ORCID'):
                    build.build_site(self.source, self.output)
                self.assertFalse(self.output.exists())

    def test_invalid_slug_or_duplicate_config_id_is_rejected(self):
        for sid in ('../outside', 'A-Wang', 'jie/wang', 'jie\\wang', 'jie-wang.json', ''):
            with self.subTest(sid=sid):
                self.write_json('scholars.json', [{**self.scholars[0], 'id': sid}])
                with self.assertRaisesRegex(ValueError, 'Invalid scholar id'):
                    build.build_site(self.source, self.output)
                self.assertFalse(self.output.exists())
        self.write_json('scholars.json', self.scholars * 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate scholar id'):
            build.build_site(self.source, self.output)

    def test_mismatched_catalog_membership_or_entry_orcid_is_rejected(self):
        self.catalog['scholars']['unexpected'] = self.catalog['scholars']['jie-wang']
        self.write_json('data/catalog.json', self.catalog)
        with self.assertRaisesRegex(ValueError, 'must match exactly'):
            build.build_site(self.source, self.output)
        del self.catalog['scholars']['unexpected']
        self.catalog['scholars']['jie-wang']['orcid'] = '0000-0001-9808-6890'
        self.write_json('data/catalog.json', self.catalog)
        with self.assertRaisesRegex(ValueError, 'does not match configuration'):
            build.build_site(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_output_cannot_overwrite_source_or_source_data(self):
        for output in (self.source, self.source.parent, self.source / 'data', self.source / 'assets/out'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                build.build_site(self.source, output)


if __name__ == '__main__':
    unittest.main()
