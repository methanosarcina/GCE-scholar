import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import publisher
import urllib.request
from publisher import parse_publisher, landing_url

class PublisherTests(unittest.TestCase):
    doi='10.1038/test-paper'
    source='https://www.nature.com/articles/test-paper'
    meta='<meta name="citation_doi" content="10.1038/test-paper">'

    def test_nature_abstract_image(self):
        html=self.meta+'<div id="Abs1-content"><p>Abstract.</p><figure><img src="https://media.springernature.com/abstract.png"></figure></div><figure><img src="body.png"></figure>'
        figures,status=parse_publisher(html,self.source,self.doi)
        self.assertEqual(status,'found_candidates')
        self.assertEqual(len(figures),1)
        self.assertEqual(figures[0]['provider'],'publisher')

    def test_graphical_heading_in_tight_section(self):
        html=self.meta+'<section><h2>Graphical Abstract</h2><img src="ga.jpg"></section><section><h2>Results</h2><img src="body.jpg"></section>'
        figures,_=parse_publisher(html,self.source,self.doi)
        self.assertEqual([x['url'] for x in figures],['https://www.nature.com/articles/ga.jpg'])

    def test_wrong_doi_rejected(self):
        html='<meta name="citation_doi" content="10.1038/wrong"><img alt="Graphical Abstract" src="ga.png">'
        self.assertEqual(parse_publisher(html,self.source,self.doi),([],'doi_mismatch'))

    def test_reference_doi_does_not_verify_article(self):
        html='<meta name="citation_reference" content="citation_doi=10.1038/test-paper"><img alt="Visual Abstract" src="ga.png">'
        self.assertEqual(parse_publisher(html,self.source,self.doi),([],'doi_not_verified'))

    def test_og_and_first_figure_not_treated_as_abstract(self):
        html=self.meta+'<meta property="og:image" content="social.png"><figure><img alt="Figure 1" src="fig1.png"></figure>'
        self.assertEqual(parse_publisher(html,self.source,self.doi),([],'no_graphic_detected'))

    def test_inline_equation_and_numbered_body_figure_in_abstract_rejected(self):
        html=self.meta+'<div id="Abs1-content"><img src="equation.png"><figure><img src="body.png"><figcaption>Figure 1. Results</figcaption></figure></div>'
        self.assertEqual(parse_publisher(html,self.source,self.doi)[0],[])

    def test_non_doi_dublin_core_identifiers_do_not_conflict(self):
        html=self.meta+'<meta name="dc.identifier" content="S0092867425000012"><meta name="dc.identifier" content="ISSN:1234-5678"><img alt="Graphical Abstract" src="ga.png">'
        self.assertEqual(len(parse_publisher(html,self.source,self.doi)[0]),1)

    def test_logo_excluded_and_https_enforced(self):
        html=self.meta+'<img alt="Visual abstract" src="http://images.edu/ga.png"><img alt="Graphical abstract" src="logo.png">'
        self.assertEqual(parse_publisher(html,self.source,self.doi)[0],[])

    def test_doi_in_url_can_verify_without_metadata(self):
        figures,_=parse_publisher('<img alt="TOC Graphic" src="ga.png">','https://pubs.acs.org/doi/10.1021/test','10.1021/test')
        self.assertEqual(len(figures),1)

    def test_legacy_redirect_uses_same_publisher_over_https(self):
        req=urllib.request.Request('https://doi.org/10.1007/test')
        redirected=publisher.PoliteRedirect().redirect_request(req,None,302,'',{},'http://link.springer.com/article/10.1007/test')
        self.assertEqual(redirected.full_url,'https://link.springer.com/article/10.1007/test')

    def test_cached_application_handles_null_images_and_preserves_orcid(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir()
            author={'authorId':{'type':'ORCID','value':'0000-0000-0000-0001'}}
            paper={'id':'MED:1','doi':self.doi,'figure':None,'authorDetails':[author]}
            fig={'kind':'摘要图','provider':'publisher','source':self.source+'?error=cookies_not_supported&code=temp','url':'https://images.edu/ga.png'}
            files={'scholars.json':[{'id':'one','orcid':author['authorId']['value']}],
                   'data/catalog.json':{'scholars':{'one':{'papers':[paper]}}},
                   'data/source-report.json':{'summary':{}},
                   'data/publisher-graphics.json':{'figures':{self.doi:fig},'attempts':{}}}
            for name,value in files.items():(root/name).write_text(json.dumps(value),encoding='utf8')
            with patch.object(publisher,'ROOT',root),patch('sys.argv',['publisher.py','--apply-only']),patch.object(publisher,'inspect',side_effect=AssertionError('Unexpected network')),patch('builtins.print'):
                publisher.main()
            result=json.loads((root/'data/catalog.json').read_text(encoding='utf8'))['scholars']['one']['papers']
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['authorDetails'],[author])
            self.assertEqual(result[0]['figure']['source'],self.source)
            self.assertEqual(result[0]['figure']['provider'],'publisher')

if __name__=='__main__':unittest.main()
