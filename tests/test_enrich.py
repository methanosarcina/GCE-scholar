import unittest
from enrich import canonical, parse_lab

class EnrichmentTests(unittest.TestCase):
    def test_doi_normalization(self):
        self.assertEqual(canonical('https://doi.org/10.1021/JACS.7B04159?download=1'),'10.1021/jacs.7b04159')

    def test_doi_preserves_balanced_parentheses(self):
        self.assertEqual(canonical('https://doi.org/10.1234/paper(2020)'), '10.1234/paper(2020)')
        self.assertEqual(canonical('(10.1234/paper).'), '10.1234/paper')

    def test_image_cannot_cross_between_citations(self):
        html='<div><p><a href="https://doi.org/10.1234/one">One</a></p><p><a href="https://doi.org/10.1234/two">Two</a><img src="two.png"></p></div>'
        records={r['doi']:r for r in parse_lab(html,'https://lab.edu/papers')}
        self.assertIsNone(records['10.1234/one']['figure'])
        self.assertEqual(records['10.1234/two']['figure']['url'],'https://lab.edu/two.png')

    def test_google_image_only_next_section(self):
        html='<section><a href="https://doi.org/10.1234/one">One</a></section><section><img src="https://images.edu/one.png"></section><section><a href="https://doi.org/10.1234/two">Two</a></section>'
        records=parse_lab(html,'https://sites.google.com/lab/papers')
        self.assertEqual(records[0]['figure']['url'],'https://images.edu/one.png')
        self.assertIsNone(records[1]['figure'])

    def test_ambiguous_google_section_is_not_assigned(self):
        html='<section><a href="https://doi.org/10.1234/one">One</a><a href="https://doi.org/10.1234/two">Two</a></section><section><img src="https://images.edu/unknown.png"></section>'
        self.assertTrue(all(r['figure'] is None for r in parse_lab(html,'https://sites.google.com/lab/papers')))

    def test_logo_is_not_a_paper_figure(self):
        html='<p><a href="https://doi.org/10.1234/one">One</a><img src="logo.png"></p>'
        self.assertIsNone(parse_lab(html,'https://lab.edu/papers')[0]['figure'])

if __name__=='__main__':unittest.main()
