import unittest
from unittest.mock import MagicMock, patch
from enrich import canonical, parse_lab, check_image

class EnrichmentTests(unittest.TestCase):
    def image_response(self, payload, content_type):
        response=MagicMock()
        response.__enter__.return_value=response
        response.headers={'Content-Type':content_type}
        response.read.return_value=payload
        return response

    def test_image_check_uses_bounded_get_for_public_image_hosts(self):
        for payload, content_type in ((b'\x89PNG\r\n\x1a\nimage', 'image/png'),
                                      (b'\xff\xd8\xffimage', 'image/jpeg')):
            with self.subTest(content_type=content_type):
                response=self.image_response(payload,content_type)
                with patch('enrich.urllib.request.urlopen',return_value=response) as opened:
                    self.assertTrue(check_image('https://lab.edu/figure'))
                self.assertEqual(opened.call_args.args[0].get_method(),'GET')
                response.read.assert_called_once_with(512)

    def test_image_check_rejects_html_even_with_image_content_type(self):
        for content_type in ('text/html','image/png'):
            with self.subTest(content_type=content_type):
                response=self.image_response(b'<!-- challenge -->\n<!DOCTYPE html><html>Verify access</html>',content_type)
                with patch('enrich.urllib.request.urlopen',return_value=response):
                    self.assertFalse(check_image('https://lab.edu/figure'))

    def test_image_check_rejects_empty_responses(self):
        with patch('enrich.urllib.request.urlopen',return_value=self.image_response(b'','image/png')):
            self.assertFalse(check_image('https://lab.edu/figure'))

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

    def test_reused_doi_with_different_images_is_conflicted(self):
        # Official pages can accidentally reuse a previous paper's DOI link.
        html='''<div><p><a href="https://doi.org/10.1021/jacs.5c00199">Phosphorescent protein</a>
          <img src="phosphorescent.jpeg"></p>
          <p><a href="https://doi.org/10.1021/jacs.5c00199">Gasdermin evolution</a>
          <img src="gasdermin.jpeg"></p></div>'''
        record=parse_lab(html,'https://lab.edu/papers')[0]
        self.assertIsNone(record['figure'])
        self.assertEqual(record['imageStatus'],'conflicting-images')

    def test_duplicate_citation_with_same_image_is_not_conflicted(self):
        html='''<p><a href="https://doi.org/10.1234/one">One</a><img src="one.png"></p>
          <p><a href="https://doi.org/10.1234/one">One again</a><img src="/one.png"></p>'''
        record=parse_lab(html,'https://lab.edu/papers')[0]
        self.assertEqual(record['figure']['url'],'https://lab.edu/one.png')
        self.assertNotIn('imageStatus',record)

    def test_later_duplicate_cannot_clear_image_conflict(self):
        html=''.join('<p><a href="https://doi.org/10.1234/one">One</a><img src="'+image+'"></p>'
          for image in ('one.png','other.png','one.png'))
        record=parse_lab(html,'https://lab.edu/papers')[0]
        self.assertIsNone(record['figure'])
        self.assertEqual(record['imageStatus'],'conflicting-images')

    def test_image_conflict_does_not_affect_other_dois(self):
        html='''<p><a href="https://doi.org/10.1021/jacs.3c03701">Aspartic acids</a><img src="asp.png"></p>
          <p><a href="https://doi.org/10.1021/jacs.4c03974">Epoxide</a><img src="epoxide.png"></p>
          <p><a href="https://doi.org/10.1021/jacs.5c00199">Phosphorescent protein</a><img src="protein.jpeg"></p>
          <p><a href="https://doi.org/10.1021/jacs.5c00199">Gasdermin evolution</a><img src="gasdermin.jpeg"></p>'''
        records={r['doi']:r for r in parse_lab(html,'https://lab.edu/papers')}
        self.assertEqual(records['10.1021/jacs.3c03701']['figure']['url'],'https://lab.edu/asp.png')
        self.assertEqual(records['10.1021/jacs.4c03974']['figure']['url'],'https://lab.edu/epoxide.png')
        self.assertIsNone(records['10.1021/jacs.5c00199']['figure'])
        self.assertEqual(records['10.1021/jacs.5c00199']['imageStatus'],'conflicting-images')

    def test_wordpress_image_only_paragraph_after_citation(self):
        # Structure used on SUSTech's official publication pages.
        html='''<div><p>JACS 2023. <a href="https://doi.org/10.1021/jacs.3c03701">link</a></p>
          <p style="text-align:center">&nbsp;<img class="aligncenter wp-image-220071" src="asp.png"></p>
          <p>Another paper</p><p>JACS 2024. <a href="https://doi.org/10.1021/jacs.4c03974">link</a></p>
          <p><img src="epoxide.png"></p>
          <p>JACS 2025. <a href="https://doi.org/10.1021/jacs.5c00199">link</a></p><p><img src="protein.jpeg"></p>
          <p>Nature Chemical Biology 2025. <a href="https://doi.org/10.1021/jacs.5c00199">link</a></p><p><img src="gasdermin.png"></p></div>'''
        records={r['doi']:r for r in parse_lab(html,'https://lab.edu/papers')}
        self.assertEqual(records['10.1021/jacs.3c03701']['figure']['url'],'https://lab.edu/asp.png')
        self.assertEqual(records['10.1021/jacs.4c03974']['figure']['url'],'https://lab.edu/epoxide.png')
        self.assertIsNone(records['10.1021/jacs.5c00199']['figure'])
        self.assertEqual(records['10.1021/jacs.5c00199']['imageStatus'],'conflicting-images')

    def test_wordpress_fallback_does_not_skip_intervening_block(self):
        html='''<div><p><a href="https://doi.org/10.1234/one">One</a></p>
          <p>Next paper title</p><p><img src="other.png"></p>
          <p><a href="https://doi.org/10.1234/two">Two</a></p></div>'''
        self.assertTrue(all(r['figure'] is None for r in parse_lab(html,'https://lab.edu/papers')))

    def test_wordpress_fallback_rejects_multiple_images(self):
        html='''<div><p><a href="https://doi.org/10.1234/one">One</a></p>
          <p><img src="first.png"><img src="second.png"></p>
          <p><a href="https://doi.org/10.1234/two">Two</a></p></div>'''
        self.assertTrue(all(r['figure'] is None for r in parse_lab(html,'https://lab.edu/papers')))

    def test_wordpress_fallback_rejects_image_with_another_doi(self):
        html='''<div><p><a href="https://doi.org/10.1234/one">One</a></p>
          <p><a href="https://doi.org/10.1234/two"><img src="second.png"></a></p></div>'''
        records={r['doi']:r for r in parse_lab(html,'https://lab.edu/papers')}
        self.assertIsNone(records['10.1234/one']['figure'])
        self.assertEqual(records['10.1234/two']['figure']['url'],'https://lab.edu/second.png')

if __name__=='__main__':unittest.main()
