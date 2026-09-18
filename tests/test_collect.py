import json
import unittest
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
