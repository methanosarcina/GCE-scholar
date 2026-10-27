import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import collect

class CollectorTests(unittest.TestCase):
    def test_reject_name_only_and_wrong_identifier(self):
        oid = '0000-0001-9808-6890'
        self.assertFalse(collect.matches_orcid({'authorDetails':[{'fullName':'Luo X'}]}, oid))
        self.assertFalse(collect.matches_orcid({'authorDetails':[{'authorId':{'type':'ORCID','value':'0000-0002-0730-1151'}}]}, oid))
        self.assertTrue(collect.matches_orcid({'authorDetails':[{'authorId':{'type':'ORCID','value':oid}}]}, oid))

    def test_missing_orcid_cannot_fall_back_to_name(self):
        with self.assertRaises(ValueError):
            collect.orcid_query('')

    def test_catalog_contains_only_fixed_orcid_authors(self):
        scholars = json.loads((collect.ROOT / 'scholars.json').read_text(encoding='utf8'))
        catalog = json.loads((collect.ROOT / 'data/catalog.json').read_text(encoding='utf8'))
        self.assertEqual(len(scholars), 25)
        for scholar in scholars:
            entry = catalog['scholars'][scholar['id']]
            self.assertEqual(entry['query'], collect.orcid_query(scholar['orcid']))
            self.assertTrue(all(collect.matches_orcid(p, scholar['orcid']) for p in entry['papers']))

    def test_missing_optional_metadata(self):
        p = collect.normalize({'source':'MED','id':'1','title':'A &amp; B <i>study</i>'})
        self.assertEqual(p['title'], 'A & B study')
        self.assertEqual(p['abstract'], '')
        self.assertFalse(p['oa'])

    def test_online_date_takes_precedence_over_imputed_issue_day(self):
        p = collect.normalize({'source':'MED', 'id':'1', 'pubYear':'2026',
            'electronicPublicationDate':'2026-09-07', 'firstPublicationDate':'2026-09-01',
            'journalInfo':{'dateOfPublication':'2026 Sep', 'printPublicationDate':'2026-09-01'}})
        self.assertEqual(p['publicationDate'], '2026-09-07')
        self.assertEqual(p['dateSource'], 'online')
        self.assertEqual(p['datePrecision'], 'day')
        self.assertEqual(p['printPublicationDate'], '2026-09')

    def test_month_and_year_dates_keep_actual_precision(self):
        for raw, expected, precision in [('2026 Sep', '2026-09', 'month'), ('2026', '2026', 'year')]:
            with self.subTest(raw=raw):
                p = collect.publication_dates({'pubYear':'2026', 'firstPublicationDate':'2026-01-01',
                    'journalInfo':{'dateOfPublication':raw, 'printPublicationDate':'2026-01-01'}})
                self.assertEqual(p['publicationDate'], expected)
                self.assertEqual(p['datePrecision'], precision)

    def test_original_print_day_is_retained(self):
        p = collect.publication_dates({'pubYear':'2026', 'journalInfo':{'dateOfPublication':'2026 Sep 7'}})
        self.assertEqual(p['publicationDate'], '2026-09-07')
        self.assertEqual(p['dateSource'], 'print')

    def test_invalid_dates_and_indexing_dates_are_not_publication_dates(self):
        for value in ('2026-02-30', '2026-13', '2026 Foo', '2026 Sep 31', '0000', '<script>'):
            with self.subTest(value=value):
                self.assertEqual(collect.publication_date(value), '')
        p = collect.publication_dates({'pubYear':'2026', 'dateOfCreation':'2026-09-17',
            'dateOfRevision':'2026-10-27', 'firstIndexDate':'2026-09-18', 'firstPublicationDate':'2026-01-01'})
        self.assertEqual(p['publicationDate'], '2026')
        self.assertEqual(p['datePrecision'], 'year')

    def test_unparseable_date_ranges_fall_back_to_year(self):
        p = collect.publication_dates({'pubYear':'2026', 'journalInfo':{'dateOfPublication':'2026 Sep-Oct'}})
        self.assertEqual(p['publicationDate'], '2026')

    def test_failed_refresh_keeps_last_successful_catalog_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            scholars = [{'id':'one', 'name':'One', 'orcid':'0000-0001-9808-6890'}]
            (root / 'scholars.json').write_text(json.dumps(scholars), encoding='utf8')
            original = json.dumps({'updated':'2026-09-17', 'scholars':{}})
            path = root / 'data/catalog.json'
            path.write_text(original, encoding='utf8')
            with patch('collect.ROOT',root), patch('sys.argv',['collect.py']), patch('collect.search',side_effect=RuntimeError('HTTP 503')), patch('builtins.print'):
                with self.assertRaisesRegex(RuntimeError,'existing catalog was kept unchanged'):
                    collect.main()
            self.assertEqual(path.read_text(encoding='utf8'), original)

    def test_pagination_terminates_on_repeated_cursor(self):
        response = json.dumps({'hitCount':1,'nextCursorMark':'same','resultList':{'result':[{'source':'MED','id':'1'}]}})
        with patch('collect.fetch', return_value=response):
            self.assertIsNone(collect.search('AUTH:test','same')['cursor'])

    def test_graphical_abstract_preferred_over_body_figure(self):
        xml = '<article xmlns:xlink="http://www.w3.org/1999/xlink"><fig><caption>Figure one</caption><graphic xlink:href="body.jpg"/></fig><abstract abstract-type="graphical"><graphic xlink:href="abstract.jpg"/></abstract></article>'
        page = '<img src="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/a/body.jpg"><img src="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/a/abstract.jpg">'
        with patch('collect.fetch', side_effect=[xml,page]):
            result = collect.figure('PMC123')
            self.assertEqual(result['kind'], '摘要图')
            self.assertTrue(result['url'].endswith('/abstract.jpg'))

    def test_pmcid_rejects_untrusted_path(self):
        with self.assertRaises(ValueError):
            collect.figure('../secret')

if __name__ == '__main__':
    unittest.main()
