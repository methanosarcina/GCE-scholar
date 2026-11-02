import argparse
import copy
import datetime
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import crossref


class CrossrefTests(unittest.TestCase):
    oid = '0000-0001-7602-5050'
    other = '0000-0002-0402-7417'

    def work(self, doi='10.1021/jacs.6c15079', oid=None):
        return {'DOI': doi, 'type': 'journal-article',
                'title': ['Coupling <i>enzyme</i> activity\n to survival'],
                'container-title': ['Journal of the American\nChemical Society'],
                'abstract': '<jats:p>A <jats:italic>study</jats:italic>.</jats:p>',
                'published-online': {'date-parts': [[2026, 10, 28]]},
                'author': [{'given': 'Jie', 'family': 'Wang',
                            'ORCID': 'https://orcid.org/' + (oid or self.oid)}],
                'is-referenced-by-count': 2,
                'URL': 'javascript:malicious-link-is-not-used'}

    def scholars(self):
        return [{'id': 'jie-wang', 'name': 'Jie Wang', 'orcid': self.oid}]

    def catalog(self):
        return {'updated': 'base-update', 'scholars': {'jie-wang': {
            'papers': [], 'total': 17, 'complete': True, 'updated': 'epmc-update',
            'query': 'AUTHORID:"' + self.oid + '"', 'orcid': self.oid}}}

    def cache(self, papers):
        return {'scholars': {'jie-wang': {'orcid': self.oid,
                'lastSuccess': 'previous-success', 'papers': papers}}}

    def supplement(self, catalog, cache=None, **kwargs):
        with patch('crossref.time.sleep'), patch('builtins.print'):
            return crossref.supplement(catalog, self.scholars(), cache or {},
                                       today=datetime.date(2026, 11, 2), now='now', **kwargs)

    def test_exact_author_orcid_required_and_name_never_grants_admission(self):
        self.assertIsNotNone(crossref.normalize(self.work(), self.oid))
        self.assertIsNone(crossref.normalize(self.work(oid=self.other), self.oid))
        name_only = self.work()
        name_only['author'][0].pop('ORCID')
        self.assertIsNone(crossref.normalize(name_only, self.oid))
        name_only['author'][0]['ORCID'] = 'https://orcid.org.evil.test/' + self.oid
        self.assertIsNone(crossref.normalize(name_only, self.oid))
        name_only['author'] = None
        self.assertIsNone(crossref.normalize(name_only, self.oid))

    def test_normalized_metadata_uses_safe_doi_and_cleans_inline_markup(self):
        paper = crossref.normalize(self.work(), self.oid)
        self.assertEqual(paper['id'], 'DOI:10.1021/jacs.6c15079')
        self.assertEqual(paper['url'], 'https://doi.org/10.1021/jacs.6c15079')
        self.assertEqual(paper['metadataSource'], 'crossref')
        self.assertEqual(paper['metadataURL'], 'https://api.crossref.org/works/10.1021/jacs.6c15079')
        self.assertEqual(paper['title'], 'Coupling enzyme activity to survival')
        self.assertEqual(paper['journal'], 'Journal of the American Chemical Society')
        self.assertEqual(paper['abstract'], 'A study .')
        self.assertEqual(paper['authorDetails'][0]['authorId'], {'type': 'ORCID', 'value': self.oid})
        self.assertFalse(paper['oa'])
        self.assertEqual(paper['pmcid'], '')

    def test_malicious_doi_and_non_article_types_cannot_be_added(self):
        for doi in ('javascript:alert(1)', 'https://evil.test/10.1021/paper',
                    '10.1021/../escape', '10.1021/paper?redirect=evil',
                    '10.1021/<script>', '10.1021/paper\nmore'):
            with self.subTest(doi=doi):
                self.assertIsNone(crossref.normalize(self.work(doi), self.oid))
        for kind in ('posted-content', 'book-chapter', 'dataset', None):
            work = self.work()
            work['type'] = kind
            self.assertIsNone(crossref.normalize(work, self.oid))

    def test_publication_dates_keep_true_precision_and_ignore_deposit_dates(self):
        for parts, value, precision in (([2026], '2026', 'year'),
                                        ([2026, 10], '2026-10', 'month'),
                                        ([2026, 10, 28], '2026-10-28', 'day')):
            with self.subTest(parts=parts):
                result = crossref.dates({'published-online': {'date-parts': [parts]},
                                        'published-print': {'date-parts': [[2026, 11, 1]]}})
                self.assertEqual(result['publicationDate'], value)
                self.assertEqual(result['datePrecision'], precision)
                self.assertEqual(result['dateSource'], 'online')
        self.assertEqual(crossref.dates({'created': {'date-parts': [[2026, 10, 28]]},
                                        'deposited': {'date-parts': [[2026, 10, 29]]}})['publicationDate'], '')
        self.assertEqual(crossref.dates({'published-online': {'date-parts': [[2026, 2, 30]]},
                                        'published-print': {'date-parts': [[2026, 11]]}})['publicationDate'], '2026-11')
        self.assertEqual(crossref.dates({'published': {'date-parts': [[2026]]}})['dateSource'], 'published')

    def test_cursor_pagination_and_filter_use_fixed_orcid_and_window(self):
        first = self.work('10.1021/first')
        last = self.work('10.1021/last')
        responses = [json.dumps({'message': {'items': [first] * 200, 'next-cursor': 'next+/='}}),
                     json.dumps({'message': {'items': [last], 'next-cursor': 'unused'}})]
        with patch('collect.fetch', side_effect=responses) as fetch, patch('crossref.time.sleep'):
            papers = crossref.fetch_works(self.oid, '2025-11-02')
        self.assertEqual({paper['doi'] for paper in papers}, {'10.1021/first', '10.1021/last'})
        self.assertEqual(fetch.call_count, 2)
        first_query = urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.call_args_list[0].args[0]).query)
        second_query = urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.call_args_list[1].args[0]).query)
        self.assertEqual(first_query['filter'], ['orcid:' + self.oid + ',from-pub-date:2025-11-02'])
        self.assertEqual(first_query['rows'], ['200'])
        self.assertEqual(first_query['cursor'], ['*'])
        self.assertEqual(second_query['cursor'], ['next+/='])
        self.assertIn('abstract', first_query['select'][0].split(','))

    def test_repeated_full_page_cursor_is_a_failed_query(self):
        response = json.dumps({'message': {'items': [self.work()] * 200, 'next-cursor': '*'}})
        with patch('collect.fetch', return_value=response):
            with self.assertRaisesRegex(ValueError, 'repeated'):
                crossref.fetch_works(self.oid, '2025-11-02')

    def test_existing_europe_pmc_doi_wins_without_metadata_replacement(self):
        catalog = self.catalog()
        existing = crossref.normalize(self.work(), self.oid)
        existing.update(id='MED:123', metadataSource='europepmc', title='Europe PMC title',
                        doi=existing['doi'].upper(), figure={'url': 'https://lab.edu/existing.png'})
        catalog['scholars']['jie-wang']['papers'] = [existing]
        before = copy.deepcopy(existing)
        with patch('crossref.fetch_works', return_value=[crossref.normalize(self.work(), self.oid)]):
            cache, report = self.supplement(catalog)
        self.assertEqual(catalog['scholars']['jie-wang']['papers'], [before])
        self.assertEqual(report['summary']['addedPapers'], 0)
        self.assertEqual(catalog['scholars']['jie-wang']['crossrefCount'], 0)
        self.assertEqual(cache['scholars']['jie-wang']['papers'][0]['figure'], before['figure'])
        self.assertEqual(catalog['scholars']['jie-wang']['total'], 17)
        self.assertTrue(catalog['scholars']['jie-wang']['complete'])
        self.assertEqual(catalog['scholars']['jie-wang']['updated'], 'epmc-update')

    def test_success_merges_old_cache_outside_window_and_preserves_figures(self):
        previous = crossref.normalize(self.work('10.1021/older'), self.oid)
        previous.update(publicationDate='2020', figure={'url': 'https://lab.edu/older.png'},
                        labSources=['https://lab.edu/papers'])
        fresh = crossref.normalize(self.work(), self.oid)
        catalog = self.catalog()
        with patch('crossref.fetch_works', return_value=[fresh]):
            cache, report = self.supplement(catalog, self.cache([previous]))
        self.assertEqual(len(catalog['scholars']['jie-wang']['papers']), 2)
        self.assertEqual(report['summary']['addedPapers'], 2)
        self.assertEqual(cache['scholars']['jie-wang']['lastSuccess'], 'now')
        restored = next(paper for paper in catalog['scholars']['jie-wang']['papers'] if paper['doi'] == '10.1021/older')
        self.assertEqual(restored['figure'], previous['figure'])
        self.assertEqual(restored['labSources'], previous['labSources'])
        # Simulate the next Europe PMC-only rebuild and restore from saved cache.
        rebuilt = self.catalog()
        with patch('crossref.fetch_works', side_effect=RuntimeError('HTTP 503')):
            _, second_report = self.supplement(rebuilt, cache)
        self.assertEqual(len(rebuilt['scholars']['jie-wang']['papers']), 2)
        self.assertEqual(second_report['summary']['failedQueries'], 1)

    def test_failed_query_uses_only_prior_strictly_verified_cache(self):
        valid = crossref.normalize(self.work(), self.oid)
        wrong = copy.deepcopy(valid)
        wrong.update(doi='10.1021/wrong')
        wrong['authorDetails'][0]['authorId']['value'] = self.other
        malicious = copy.deepcopy(valid)
        malicious['doi'] = 'javascript:alert(1)'
        with patch('crossref.fetch_works', side_effect=RuntimeError('HTTP 429')):
            catalog = self.catalog()
            cache, report = self.supplement(catalog, self.cache([valid, wrong, malicious]))
        self.assertEqual([paper['doi'] for paper in catalog['scholars']['jie-wang']['papers']], [valid['doi']])
        self.assertEqual(len(cache['scholars']['jie-wang']['papers']), 1)
        self.assertEqual(cache['scholars']['jie-wang']['lastSuccess'], 'previous-success')
        self.assertEqual(report['scholars'][0]['error'], 'HTTP 429')

    def test_apply_only_uses_cache_without_network_and_copies_new_illustrations(self):
        paper = crossref.normalize(self.work(), self.oid)
        catalog = self.catalog()
        illustrated = copy.deepcopy(paper)
        illustrated.update(figure={'url': 'https://lab.edu/new.png'}, labSources=['https://lab.edu/new'])
        catalog['scholars']['jie-wang']['papers'] = [illustrated]
        with patch('crossref.fetch_works', side_effect=AssertionError('network forbidden')):
            cache, report = self.supplement(catalog, self.cache([paper]), apply_only=True)
        self.assertEqual(cache['scholars']['jie-wang']['papers'][0]['figure'], illustrated['figure'])
        self.assertEqual(cache['scholars']['jie-wang']['papers'][0]['labSources'], illustrated['labSources'])
        self.assertEqual(report['summary']['successfulQueries'], 0)

    def test_cli_writes_cache_and_preserves_other_source_report_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            (root / 'scholars.json').write_text(json.dumps(self.scholars()), encoding='utf8')
            (root / 'data/catalog.json').write_text(json.dumps(self.catalog()), encoding='utf8')
            (root / 'data/crossref.json').write_text(json.dumps(self.cache([crossref.normalize(self.work(), self.oid)])), encoding='utf8')
            (root / 'data/source-report.json').write_text(json.dumps({'sources': [{'status': 'ok'}], 'publisher': {'kept': True}}), encoding='utf8')
            with patch('crossref.ROOT', root), patch('sys.argv', ['crossref.py', '--apply-only']), patch('collect.fetch', side_effect=AssertionError('network')), patch('builtins.print'):
                crossref.main()
            report = json.loads((root / 'data/source-report.json').read_text(encoding='utf8'))
            self.assertEqual(report['sources'], [{'status': 'ok'}])
            self.assertEqual(report['publisher'], {'kept': True})
            self.assertEqual(report['crossref']['summary']['addedPapers'], 1)
            self.assertTrue((root / 'data/crossref.json').exists())

    def test_unknown_scholar_or_nonpositive_window_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown scholar'):
            self.supplement(self.catalog(), selected=['not-configured'])
        for value in ('0', '-1', 'abc', '1.5'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                crossref.positive_days(value)
        self.assertEqual(crossref.positive_days('365'), 365)


if __name__ == '__main__':
    unittest.main()
