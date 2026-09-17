import json
import unittest
from unittest.mock import patch
import collect

class CollectorTests(unittest.TestCase):
    def test_missing_optional_metadata(self):
        p = collect.normalize({'source':'MED','id':'1','title':'A &amp; B <i>study</i>'})
        self.assertEqual(p['title'], 'A & B  study')
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
