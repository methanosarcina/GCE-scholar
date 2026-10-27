import unittest
import io
import base64
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

    def test_acs_visual_abstract_in_nested_silverchair_section(self):
        doi='10.1021/acschembio.6c00476'
        source='https://pubs.acs.org/acbcct/article-abstract/21/10/2611/5427262/article'
        image='https://acs.silverchair-cdn.com/acs/abstract.png?Expires=123&amp;Signature=public'
        html='<meta name="citation_doi" content="'+doi+'"><div class="figure-table-wrapper graphical-abstract"><h2>Visual Abstract</h2><div class="fig"><a><img src="'+image+'" alt="Figure. Refer to the image caption for details."></a></div></div><div class="fig-modal"><img src="'+image+'"></div><figure><img src="body.png"></figure>'
        figures,status=parse_publisher(html,source,doi)
        self.assertEqual(status,'found_candidates')
        self.assertEqual(len(figures),1)
        self.assertEqual(figures[0]['doi'],doi)
        self.assertIn('Signature=public',figures[0]['url'])

    def image_response(self, payload, mime='image/png'):
        response=io.BytesIO(payload)
        response.headers={'Content-Type':mime}
        return response

    def test_signed_image_is_cached_without_publishing_expiring_query(self):
        payload=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jA1cAAAAASUVORK5CYII=')
        fig={'url':'https://acs.silverchair-cdn.com/abstract.png?Expires=123&Signature=public','provider':'publisher','source':self.source,'kind':'摘要图'}
        with tempfile.TemporaryDirectory() as folder, patch.object(publisher,'ROOT',Path(folder)), patch.object(publisher.urllib.request,'urlopen',return_value=self.image_response(payload)) as request:
            cached=publisher.verify_image(fig)
            self.assertEqual(request.call_args.args[0].get_method(),'GET')
            self.assertEqual(request.call_args.args[0].full_url,fig['url'])
            self.assertRegex(cached['url'],r'^assets/publisher/[a-f0-9]{32}\.png$')
            self.assertEqual((Path(folder)/cached['url']).read_bytes(),payload)
            self.assertEqual(cached['publisherAsset'],'https://acs.silverchair-cdn.com/abstract.png')
            self.assertNotIn('Signature',__import__('json').dumps(cached))
            self.assertEqual(cached['source'],self.source)

    def test_repository_binary_mime_is_accepted_only_for_verified_image_bytes(self):
        payload=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jA1cAAAAASUVORK5CYII=')
        fig={'url':'https://pmc-oa-opendata.s3.amazonaws.com/PMC123.1/ga.png','kind':'摘要图'}
        with tempfile.TemporaryDirectory() as folder, patch.object(publisher,'ROOT',Path(folder)), patch.object(publisher.urllib.request,'urlopen',return_value=self.image_response(payload,'application/octet-stream')):
            self.assertEqual(publisher.verify_image(fig,force_cache=True)['storage'],'local')
        with patch.object(publisher.urllib.request,'urlopen',return_value=self.image_response(b'not an image','application/octet-stream')):
            with self.assertRaisesRegex(ValueError,'invalid publisher image'):
                publisher.verify_image(fig,force_cache=True)

    def test_public_static_image_uses_get_and_keeps_original_url(self):
        fig={'url':'https://images.edu/abstract.png','source':self.source}
        with patch.object(publisher.urllib.request,'urlopen',return_value=self.image_response(b'PNG data')) as request:
            self.assertEqual(publisher.verify_image(fig),fig)
            self.assertEqual(request.call_args.args[0].get_method(),'GET')

    def test_access_challenge_html_is_not_an_image(self):
        fig={'url':'https://images.edu/abstract.png?Signature=public'}
        with patch.object(publisher.urllib.request,'urlopen',return_value=self.image_response(b'<html>Access denied</html>','text/html')):
            with self.assertRaisesRegex(ValueError,'did not return an image'):
                publisher.verify_image(fig)

    def test_snapshot_cannot_add_an_unknown_doi_or_use_mismatched_metadata(self):
        snapshot={'doi':self.doi,'source':self.source,'html':'<meta name="citation_doi" content="10.1038/wrong"><img alt="Visual Abstract" src="ga.png">'}
        with patch.object(publisher,'verify_image',side_effect=AssertionError('Unexpected request')):
            with self.assertRaisesRegex(ValueError,'existing ORCID-qualified catalog'):
                publisher.inspect_snapshot(snapshot,{})
            doi,fig,status=publisher.inspect_snapshot(snapshot,{self.doi:[]})
            self.assertEqual(status['status'],'doi_mismatch')
            self.assertIsNone(fig)

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
