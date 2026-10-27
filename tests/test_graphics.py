import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import graphics

DOI = '10.1021/test.1'
PMCID = 'PMC123'
FEED = 'https://pubs.acs.org/rss/acbcct/currentIssue.xml'
IMAGE = 'https://acs.silverchair-cdn.com/abstract.png?Expires=999&amp;Signature=public'
RSS = ('<rss xmlns:prism="prism"><channel><item><title>Test</title>'
       '<link>https://pubs.acs.org/acbcct/article/1/1/1/2/test</link>'
       '<prism:doi>'+DOI+'</prism:doi>'
       '<description><![CDATA[<img src="'+IMAGE+'" alt="Paper title">]]></description>'
       '</item></channel></rss>').encode()


class AutomaticGraphicsTests(unittest.TestCase):
    def test_feed_registry_can_support_other_publishers_without_article_code(self):
        feeds=['https://publisher.example/chemistry/rss.xml']
        self.assertEqual(graphics.registered_feeds({'journal':'Any journal','feeds':feeds}),feeds)
        self.assertEqual(graphics.registered_feeds({'feeds':['javascript:alert(1)','http://publisher.example/rss']}),[])

    def test_rss_uses_exact_doi_and_decodes_image_without_claiming_abstract(self):
        found = graphics.parse_feed(RSS, FEED)
        self.assertEqual(set(found), {DOI})
        self.assertIn('&Signature=public', found[DOI]['url'])
        self.assertNotIn('&amp;', found[DOI]['url'])
        self.assertEqual(found[DOI]['kind'], '期刊目录图')
        self.assertEqual(found[DOI]['provider'], 'publisher-rss')

    def test_explicit_rss_graphical_abstract_is_labeled_as_such(self):
        feed = RSS.replace(b'alt="Paper title"', b'alt="Graphical Abstract"')
        self.assertEqual(graphics.parse_feed(feed, FEED)[DOI]['kind'], '摘要图')

    def test_conflicting_rss_dois_are_rejected(self):
        feed = RSS.replace(b'</prism:doi>', b'</prism:doi><prism:doi>10.1021/wrong</prism:doi>')
        self.assertEqual(graphics.parse_feed(feed, FEED), {})

    def test_repository_listing_does_not_mix_article_ids_or_versions(self):
        listing = b'<List><Contents><Key>PMC123.2/PMC123.2.json</Key></Contents><Contents><Key>PMC1234.1/PMC1234.1.json</Key></Contents><Contents><Key>PMC123.1/PMC123.2.json</Key></Contents></List>'
        self.assertEqual(graphics.parse_s3_listing(listing, PMCID), ['PMC123.2/PMC123.2.json'])

    def metadata(self):
        return {'pmcid':PMCID, 'doi':DOI, 'version':1, 'license_code':'CC BY',
                'media_urls':['s3://pmc-oa-opendata/PMC123.1/ga.jpg?md5=public',
                              's3://pmc-oa-opendata/PMC123.1/body.jpg']}

    def jats(self):
        return ('<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta>'
                '<article-id pub-id-type="doi">'+DOI+'</article-id>'
                '<abstract abstract-type="graphical"><title>Graphical Abstract</title>'
                '<graphic xlink:href="ga.tif"/></abstract></article-meta></front>'
                '<body><fig><label>Figure 1</label><graphic xlink:href="body.jpg"/></fig></body></article>').encode()

    def test_jats_only_returns_explicit_abstract_and_disclosed_media(self):
        figures, status = graphics.parse_jats(self.jats(), self.metadata(), DOI)
        self.assertEqual(status, 'found_candidates')
        self.assertEqual(len(figures), 1)
        self.assertIn('/ga.jpg', figures[0]['url'])
        self.assertEqual(figures[0]['match'], 'exact-doi-and-pmcid')
        self.assertEqual(figures[0]['license'], 'CC BY')

    def test_graphical_abstract_without_disclosed_media_is_not_called_absent(self):
        metadata=self.metadata()
        metadata['media_urls']=['s3://pmc-oa-opendata/PMC123.1/body.jpg']
        self.assertEqual(graphics.parse_jats(self.jats(),metadata,DOI),([], 'abstract_media_unavailable'))

    def test_body_figure_alone_is_not_a_graphical_abstract(self):
        xml = ('<article><front><article-meta><article-id pub-id-type="doi">'+DOI+
               '</article-id></article-meta></front><body><fig><label>Figure 1</label>'
               '</fig></body></article>').encode()
        self.assertEqual(graphics.parse_jats(xml, self.metadata(), DOI), ([], 'no_graphic_detected'))

    def test_repository_doi_mismatch_and_unapproved_hosts_rejected(self):
        self.assertEqual(graphics.parse_jats(self.jats(), {**self.metadata(),'doi':'10.1021/wrong'}, DOI), ([], 'doi_mismatch'))
        self.assertIsNone(graphics.s3_url('https://example.org/PMC123.1/ga.jpg'))
        self.assertIsNone(graphics.s3_url('s3://another-bucket/PMC123.1/ga.jpg'))

    def test_retry_dates_and_local_cache_integrity(self):
        self.assertTrue(graphics.due({}))
        future = (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=1)).isoformat()
        self.assertFalse(graphics.due({'retryAfter':future}))
        with tempfile.TemporaryDirectory() as folder, patch.object(graphics,'ROOT',Path(folder)):
            name='assets/publisher/'+'a'*32+'.png'
            path=Path(folder)/name;path.parent.mkdir(parents=True);path.write_bytes(b'cached')
            self.assertTrue(graphics.valid_cached({'url':name,'sha256':hashlib.sha256(b'cached').hexdigest()}))
            self.assertFalse(graphics.valid_cached({'url':name,'sha256':'bad'}))
            self.assertFalse(graphics.valid_cached({'url':'../private.png'}))

    def test_from_scratch_batch_does_not_use_a_page_snapshot_or_add_papers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);(root/'data').mkdir()
            author={'authorId':{'type':'ORCID','value':'0000-0000-0000-0001'}}
            paper={'id':'MED:1','doi':DOI,'journal':'ACS chemical biology','year':'2026','authorDetails':[author]}
            catalog={'scholars':{'one':{'papers':[paper]}}}
            files={'scholars.json':[{'id':'one','orcid':author['authorId']['value']}],
                   'data/catalog.json':catalog, 'data/source-report.json':{'summary':{}},
                   'publisher-feeds.json':{'source':'https://pubs.acs.org/pages/rss','journals':[{'journal':'ACS chemical biology','code':'acbcct'}]}}
            for name,value in files.items():
                (root/name).write_text(json.dumps(value),encoding='utf8')
            feed = RSS.replace(b'</channel>', b'<item><link>https://doi.org/10.1021/unknown</link><description>&lt;img src="https://img.edu/ga.png"&gt;</description></item></channel>')
            def cache_image(fig, force_cache=False):
                self.assertTrue(force_cache)
                name='assets/publisher/'+'b'*32+'.png'
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'cached image')
                return {**fig,'url':name,'storage':'local'}
            with patch.object(graphics,'ROOT',root),patch.object(graphics,'get_bytes',return_value=feed),patch.object(graphics,'verify_image',side_effect=cache_image),patch('publisher.inspect_snapshot',side_effect=AssertionError('Manual page snapshot used')),patch('sys.argv',['graphics.py','--rss-only']),patch('builtins.print'):
                graphics.main()
            result=json.loads((root/'data/catalog.json').read_text(encoding='utf8'))
            papers=result['scholars']['one']['papers']
            self.assertEqual(len(papers),1)
            self.assertEqual(papers[0]['authorDetails'],[author])
            self.assertEqual(papers[0]['figure']['doi'],DOI)
            self.assertEqual(papers[0]['figure']['provider'],'publisher-rss')
            cache=json.loads((root/'data/automatic-graphics.json').read_text(encoding='utf8'))
            self.assertEqual(set(cache['figures']),{DOI})
            self.assertEqual(cache['summary']['addedImages'],1)

    def test_apply_never_downgrades_a_verified_abstract_to_rss_catalog_image(self):
        abstract={'url':'https://publisher.edu/ga.png','kind':'摘要图','provider':'publisher'}
        paper={'figure':abstract};catalog={'scholars':{'one':{'papers':[paper]}}}
        with patch.object(graphics,'valid_cached',return_value=True):
            graphics.apply_figures(catalog,{DOI:[paper]},{DOI:{'kind':'期刊目录图','url':'assets/ga.png'}})
        self.assertEqual(paper['figure'],abstract)


if __name__ == '__main__':
    unittest.main()
