import os, json

from unittest.mock import patch
from datetime import datetime
import mock

from django.test import TestCase, override_settings
from django.conf import settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from submission.models import STAGE_PUBLISHED, Licence, Keyword, Field, FieldAnswer
from submission.models import FrozenAuthor

import utils
from utils.testing import helpers

from core.models import File, SupplementaryFile
from core.files import save_file
# these imports are needed to make sure plugin urls are loaded
from core import models as core_models, urls # pylint: disable=unused-import
from identifiers.models import Identifier

from plugins.eschol import logic
from plugins.eschol.models import EscholArticle

TEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD v1.2 20120330//EN" "http://jats.nlm.nih.gov/publishing/1.2/JATS-journalpublishing1.dtd">
<article>test</article>
"""

DEPOSIT_RESULT = """Escholarhip Deposit for Article {0}: \
{{'item': {{'sourceName': 'janeway', 'sourceID': '{0}', 'sourceURL': 'localhost', \
'submitterEmail': 'user1@test.edu', 'title': 'Test Article from Utils Testing Helpers', \
'type': 'ARTICLE', 'published': '2023-01-01', 'isPeerReviewed': True, \
'contentVersion': 'PUBLISHER_VERSION', 'journal': 'Journal One', 'units': ['TST'], \
'pubRelation': 'EXTERNAL_PUB', 'datePublished': '2023-01-01', 'sectionHeader': 'Article', \
'volume': '0', 'issue': '0', 'issueTitle': 'Test Issue from Utils Testing Helpers', \
'issueDate': '2022-01-01', 'orderInSection': 10001, 'localIDs': [{{'id': 'janeway_{0}', \
'scheme': 'OTHER_ID', 'subScheme': 'other'}}]}}}}"""


class Response(object):
    def __init__(self, text):
        self.text = text

class EscholConnectorTest(TestCase):

    def setUp(self):
        # unconfigure ESCHOL API to start
        del settings.ESCHOL_API_URL

        self.user = helpers.create_user("user1@test.edu")
        self.request = helpers.Request()
        self.request.user = self.user
        self.press = helpers.create_press()
        self.journal, _ = helpers.create_journals()
        d = datetime(2023, 1, 1, tzinfo=timezone.get_current_timezone())
        self.article = helpers.create_article(self.journal,
                                              with_author=False,
                                              date_published=d,
                                              stage=STAGE_PUBLISHED,
                                              language=None)
        self.article.owner = self.user
        self.article.save()

    def create_file(self, article, file, label):
        path_parts = ('articles', article.pk)

        return save_file(self.request, file, label=label, public=True, path_parts=path_parts,)

    @override_settings(JSCHOL_URL="test.test/")
    def test_short_ark(self):
        e = EscholArticle.objects.create(article=self.article,
                                         ark="ark:/13030/qtXXXXXXXX")
        self.assertEqual(e.get_short_ark(), "XXXXXXXX")
        self.assertEqual(e.get_eschol_url(), "test.test/uc/item/XXXXXXXX")

    def test_has_doi_error(self):
        e = EscholArticle.objects.create(article=self.article, ark="ark:/13030/qtXXXXXXXX")
        self.assertFalse(e.is_doi_registered)
        self.assertFalse(e.has_doi_error())

        e.is_doi_registered = True
        self.assertFalse(e.has_doi_error())

        e.doi_result_text = "success"
        self.assertFalse(e.has_doi_error())

        e.doi_result_text = "failed"
        self.assertTrue(e.has_doi_error())

        e.is_doi_registered = False
        self.assertTrue(e.has_doi_error())


    def test_xml_to_html_galley(self):
        xml_filepath = f'{os.path.dirname(__file__)}/test_files/glossa_test.xml'

        with open(xml_filepath, 'rb') as f:
            xml_file = SimpleUploadedFile("test.xml", f.read())
        xml_obj = self.create_file(self.article, xml_file, "Test XML File")
        galley = helpers.create_galley(self.article, file_obj=xml_obj)
        self.article.render_galley = galley

        img_file = SimpleUploadedFile("test.png", b"\x00\x01\x02\x03")
        img_obj = self.create_file(self.article, img_file, "Img file 1")
        galley.images.add(img_obj)
        galley.save()

        pdf_file = SimpleUploadedFile("test.pdf", b"\x00\x01\x02\x03")
        pdf_obj = self.create_file(self.article, pdf_file, "Test PDF File")
        supp_pdf = SupplementaryFile.objects.create(file=pdf_obj)
        self.article.supplementary_files.add(supp_pdf)

        self.article.save()

        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))

        base_url = "http://localhost/TST/plugins/escholarship-publishing-plugin/download/"
        self.assertEqual(j['id'], 'ark:/13030/qtXXXXXXXX')
        url = f"{base_url}{self.article.pk}/file/"
        self.assertIn(url, j["contentLink"])
        self.assertEqual(j["contentFileName"], 'qtXXXXXXXX.html')

        supp_files = j['suppFiles']
        self.assertEqual(len(supp_files), 2)

        base_furl = f"{base_url}{self.article.pk}/file/"
        sfile0 = supp_files[0]
        self.assertEqual(sfile0['file'], 'qtXXXXXXXX.xml')
        self.assertEqual(sfile0['contentType'], 'application/xml')
        self.assertEqual(sfile0['size'], 157291)
        self.assertIn(f"{base_furl}{xml_obj.pk}/?access=", sfile0['fetchLink'])
        self.assertEqual(sfile0['title'], '[XML] Test Article from Utils Testing Helpers')

        sfile1 = supp_files[1]
        self.assertEqual(sfile1['file'], 'test.pdf')
        self.assertEqual(sfile1['contentType'], 'application/pdf')
        self.assertEqual(sfile1['size'], 4)
        self.assertIn(f"{base_furl}{pdf_obj.pk}/?access=", sfile1['fetchLink'])
        #self.assertEqual(sfile1['title'], '')

        self.assertEqual(len(j['imgFiles']), 1)
        self.assertEqual(j['imgFiles'][0]['file'], 'test.png')
        self.assertIn(f"{base_furl}{img_obj.pk}/?access=", j['imgFiles'][0]['fetchLink'])

    def test_galley(self):
        f = File.objects.create(article_id=self.article.pk,
                                label="file",
                                is_galley=True,
                                original_filename="test.pdf",
                                mime_type="application/pdf",
                                uuid_filename="uuid.pdf")
        _galley = helpers.create_galley(self.article, file_obj=f)

        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))

        base_url = "http://localhost/TST/plugins/escholarship-publishing-plugin/download/"
        self.assertIn(f"{base_url}{self.article.pk}/file/{f.pk}/?access=", j["contentLink"])
        self.assertEqual(j["contentFileName"], "test.pdf")

    def test_supp_files(self):
        f1 = SimpleUploadedFile(
            "test.pdf",
            b"\x00\x01\x02\x03",
        )
        tf1 = self.create_file(self.article, f1, "Test File 1")

        f2 = SimpleUploadedFile("test.xml", TEST_XML.strip().encode("utf-8"),)
        tf2 = self.create_file(self.article, f2, "Test File 2")

        sf1 = SupplementaryFile.objects.create(file=tf1)
        self.article.supplementary_files.add(sf1)

        sf2 = SupplementaryFile.objects.create(file=tf2)
        self.article.supplementary_files.add(sf2)

        self.article.save()

        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertEqual(len(j['suppFiles']), 2)

        base_url = "http://localhost/TST/plugins/escholarship-publishing-plugin/download/"
        base_furl = f"{base_url}{self.article.pk}/file/"
        self.assertEqual(j['suppFiles'][0]['file'], 'test.pdf')
        self.assertEqual(j['suppFiles'][0]['contentType'], 'application/pdf')
        self.assertEqual(j['suppFiles'][0]['size'], 4)
        self.assertIn(f"{base_furl}{tf1.pk}/?access=", j['suppFiles'][0]['fetchLink'])

        self.assertEqual(j['suppFiles'][1]['file'], 'test.xml')
        self.assertEqual(j['suppFiles'][1]['contentType'], 'application/xml')
        self.assertEqual(j['suppFiles'][1]['size'], 226)
        self.assertIn(f"{base_furl}{tf2.pk}/?access=", j['suppFiles'][1]['fetchLink'])


    def test_invalid_license(self):
        l, _ = Licence.objects.get_or_create(journal=self.journal,
                                             press=self.press,
                                             name="Creative Commons 4",
                                             short_name="CC4",
                                             url="https://bad.url")
        l.save()
        self.article.license = l
        self.article.save()

        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertNotIn("license", j)


    def test_data_availability(self):
        field1 = Field.objects.create(journal=self.journal,
                                      press=self.press,
                                      name="Data Availability",
                                      kind="text",
                                      order=1,
                                      required=False)
        _answer1 = FieldAnswer.objects.create(field=field1,
                                             article=self.article,
                                             answer="Public repository")

        field2 = Field.objects.create(journal=self.journal,
                                      press=self.press,
                                      name="Data URL",
                                      kind="text",
                                      order=2,
                                      required=False)
        _answer2 = FieldAnswer.objects.create(field=field2,
                                             article=self.article,
                                             answer="http://data.repo")

        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertEqual(j["dataAvailability"], "publicRepo")
        self.assertEqual(j["dataURL"], "http://data.repo")

    def test_plural_sections(self):
        d = datetime(2023, 1, 1, tzinfo=timezone.get_current_timezone())
        article2 = helpers.create_article(self.journal,
                                          with_author=False,
                                          date_published=d)

        _issue = helpers.create_issue(self.journal, articles=[self.article, article2])

        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))
        self.assertEqual(j["sectionHeader"], "Articles")

    def test_minimal_json(self):
        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))
        self.assertEqual(j["sourceName"], "janeway")
        self.assertEqual(j["sourceID"], str(self.article.pk))
        self.assertEqual(j["sourceURL"], self.press.domain)
        self.assertEqual(j["submitterEmail"], self.user.email)
        self.assertEqual(j["title"], self.article.title)
        self.assertEqual(j["type"], "ARTICLE")
        self.assertEqual(j["published"], self.article.date_published.strftime("%Y-%m-%d"))
        self.assertEqual(j["datePublished"], self.article.date_published.strftime("%Y-%m-%d"))
        self.assertEqual(j["isPeerReviewed"], self.article.peer_reviewed)
        self.assertEqual(j["contentVersion"], "PUBLISHER_VERSION")
        self.assertEqual(j["journal"], self.journal.name)
        self.assertEqual(len(j["units"]), 1)
        self.assertEqual(j["units"][0], self.journal.code)
        self.assertEqual(j["pubRelation"], "EXTERNAL_PUB")
        self.assertEqual(len(j["localIDs"]), 1)
        self.assertEqual(j["localIDs"][0]["id"], f'janeway_{self.article.pk}')
        self.assertEqual(len(j), 16)

    def test_kitchen_sink(self):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        issue.issue_description = "Test issue description<br>"
        issue.save()
        cc_url = "https://creativecommons.org/licenses/by/4.0"
        l, _ = Licence.objects.get_or_create(journal=self.journal,
                                             press=self.press,
                                             name="Creative Commons 4",
                                             short_name="CC4",
                                             url=cc_url)
        l.save()
        author = helpers.create_author(self.journal)
        author.orcid =  "0000-0000-0000-0000"
        author.save()
        _corporate_author  = FrozenAuthor.objects.create(article=self.article,
                                                         institution="Author Collective",
                                                         is_corporate=True,
                                                         order=2)
        #funder, _ = Funder.objects.get_or_create(name="Test Funder",
        # fundref_id="http://dx.doi.org/10.13039/501100021082")
        #funder.save()
        doi = Identifier.objects.create(id_type="doi", identifier="10.00000/AA0000A0", article=self.article)
        other_id = Identifier.objects.create(id_type="pubid", identifier="1", article=self.article)

        self.article.abstract = "This is the abstract"
        self.article.date_submitted = datetime(2022, 1, 1, tzinfo=timezone.get_current_timezone())
        self.article.date_accepted = datetime(2022, 2, 2, tzinfo=timezone.get_current_timezone())
        self.article.custom_how_to_cite = "Citation, blah. 2023"
        self.article.first_page = 1
        self.article.last_page = 2
        self.article.language = "eng"
        self.article.publisher_name = "The Publisher Name"
        self.article.keywords.add(Keyword.objects.create(word="keyword1"))
        self.article.license = l
        self.article.authors.add(author)
        #self.article.funders.add(funder)

        self.article.save()
        author.snapshot_self(self.article)

        self.journal.issn = "1111-1111"
        self.journal.save()

        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))
        self.assertEqual(j["sourceName"], "janeway")
        self.assertEqual(j["sourceID"], str(self.article.pk))
        self.assertEqual(j["sourceURL"], self.press.domain)
        self.assertEqual(j["submitterEmail"], self.user.email)
        self.assertEqual(j["title"], self.article.title)
        self.assertEqual(j["type"], "ARTICLE")
        self.assertEqual(j["published"], self.article.date_published.strftime("%Y-%m-%d"))
        self.assertEqual(j["datePublished"], self.article.date_published.strftime("%Y-%m-%d"))
        self.assertEqual(j["isPeerReviewed"], self.article.peer_reviewed)
        self.assertEqual(j["contentVersion"], "PUBLISHER_VERSION")
        self.assertEqual(j["journal"], self.journal.name)
        self.assertEqual(len(j["units"]), 1)
        self.assertEqual(j["units"][0], self.journal.code)
        self.assertEqual(j["pubRelation"], "EXTERNAL_PUB")
        self.assertEqual(j["abstract"], "This is the abstract")
        self.assertEqual(j["dateSubmitted"], "2022-01-01")
        self.assertEqual(j["dateAccepted"], "2022-02-02")
        self.assertEqual(j["customCitation"], "Citation, blah. 2023")
        self.assertEqual(j["fpage"], '1')
        self.assertEqual(j["lpage"], '2')
        self.assertEqual(j["language"], 'eng')
        self.assertEqual(j["sectionHeader"], 'Article')
        self.assertEqual(len(j["keywords"]), 1)
        self.assertEqual(j["keywords"][0], 'keyword1')
        self.assertEqual(j["rights"], 'https://creativecommons.org/licenses/by/4.0/')
        self.assertEqual(j["publisher"], 'The Publisher Name')
        self.assertEqual(j["volume"], '0')
        self.assertEqual(j["issue"], '0')
        self.assertEqual(j["issueTitle"], 'Test Issue from Utils Testing Helpers')
        self.assertEqual(j["issueDate"], '2022-01-01')
        self.assertEqual(j["issueDescription"], "Test issue description<br>")
        self.assertEqual(j["orderInSection"], 10001)
        self.assertEqual(len(j["localIDs"]), 3)
        self.assertEqual(j["localIDs"][0]["id"], other_id.identifier)
        self.assertEqual(j["localIDs"][0]["scheme"], 'OTHER_ID')
        self.assertEqual(j["localIDs"][0]["subScheme"], 'pubid')
        self.assertEqual(j["localIDs"][1]["id"], doi.identifier)
        self.assertEqual(j["localIDs"][1]["scheme"], 'DOI')
        self.assertEqual(j["localIDs"][2]["id"], f'janeway_{self.article.pk}')
        self.assertEqual(j["localIDs"][2]["scheme"], 'OTHER_ID')
        self.assertEqual(j["localIDs"][2]["subScheme"], 'other')
        self.assertEqual(len(j["authors"]), 2)
        self.assertEqual(j["authors"][0]['nameParts']['fname'], "Author")
        self.assertEqual(j["authors"][0]['nameParts']['lname'], "User")
        self.assertEqual(j["authors"][0]['nameParts']['institution'], "Author institution")
        self.assertEqual(j["authors"][0]['nameParts']['mname'], "A")
        self.assertEqual(j["authors"][0]['email'], "authoruser@martineve.com")
        self.assertEqual(j["authors"][0]['orcid'], "0000-0000-0000-0000")
        self.assertEqual(j["authors"][1]['nameParts']['organization'], "Author Collective")
        #self.assertEqual(len(j["grants"]), 1)
        #self.assertEqual(j["grants"][0]["name"], "Test Funder")
        #self.assertEqual(j["grants"][0]["reference"], "http://dx.doi.org/10.13039/501100021082")

        self.assertEqual(len(j), 33)

    def test_ojs_source(self):
        EscholArticle.objects.create(article=self.article,
                                     ark="qt0000000",
                                     source_name="ojs",
                                     source_id="555555")
        j, _ = logic.get_article_json(self.article, logic.get_unit(self.journal))
        self.assertEqual(j["sourceName"], "ojs")
        self.assertEqual(j["sourceID"], "555555")

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'info')
    def test_send_article_no_issue(self, info_mock):
        apub = logic.send_article(self.article, False, None)
        msg = f'{self.article} published without issue'
        self.assertEqual(apub.article, self.article)
        self.assertFalse(apub.success)
        self.assertEqual(apub.result, msg)
        info_mock.assert_called_once_with(msg)

    @override_settings(ESCHOL_API_URL="test")
    @mock.patch('plugins.eschol.logic.send_to_eschol')
    def test_article_to_eschol(self, mock_send):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        self.article.primary_issue = issue
        self.article.issues.add(issue)
        self.article.save()

        result_json = {'data': {'depositItem': {'message': 'Deposited', 'id': 'ark:/13030/qtAAAAAAAA'}}}
        mock_send.return_value = Response(json.dumps(result_json))

        apub = logic.article_to_eschol(article=self.article)
        self.assertTrue(apub.success)

    @mock.patch('plugins.eschol.logic.send_to_eschol')
    def test_issue_meta_with_cover(self, mock_send):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        svg_data = """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="50"></circle>
            </svg>
        """
        svg_file = SimpleUploadedFile(
            "file.svg",
            svg_data.encode("utf-8"),
        )
        issue.cover_image = svg_file
        issue.save()

        result_json = {'data': {'updateIssue': {'message': 'Cover Image uploaded'}}}
        mock_send.return_value = Response(json.dumps(result_json))

        success, msg = logic.send_issue_meta(issue, configured=True)
        self.assertTrue(success)
        self.assertTrue(msg, "Cover Image uploaded")

 
    @patch.object(utils.logger.PrefixedLoggerAdapter, 'debug')
    def test_article_to_eschol_disabled(self, debug_mock):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        self.article.primary_issue = issue
        self.article.issues.add(issue)
        self.article.save()
        _apub = logic.article_to_eschol(article=self.article)
        result_text = DEPOSIT_RESULT.format(self.article.pk)
        debug_mock.assert_called_once_with(result_text)

    def test_private_render_galley(self):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        f = File.objects.create(article_id=self.article.pk,
                                label="file",
                                is_galley=True,
                                original_filename="test.pdf",
                                mime_type="application/pdf",
                                uuid_filename="uuid.pdf")
        galley = helpers.create_galley(self.article, file_obj=f, public=False)

        self.article.primary_issue = issue
        self.article.issues.add(issue)
        self.article.render_galley = galley
        self.article.save()
        apub = logic.send_article(self.article, False, None)

        self.assertFalse(apub.success)
        self.assertEqual(apub.result, f"Private render galley selected for {self.article}")
        self.assertEqual(EscholArticle.objects.filter(article=self.article).count(), 0)

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'debug')
    def test_issue_to_eschol(self, debug_mock):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        ipub = logic.issue_to_eschol(issue=issue)
        self.assertEqual(ipub.issue, issue)
        self.assertFalse(ipub.success)
        self.assertEqual(ipub.articlepublicationhistory_set.all().count(), 1)
        self.assertFalse(ipub.articlepublicationhistory_set.all().first().success)
        result_text = DEPOSIT_RESULT.format(self.article.pk)
        debug_mock.assert_called_once_with(result_text)

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'info')
    def test_is_not_configured(self, info_mock):
        self.assertFalse(logic.is_configured())
        info_mock.assert_called_once_with("Escholarship API not configured.")

    @override_settings(ESCHOL_API_URL="test")
    def test_is_configured(self):
        self.assertTrue(logic.is_configured())

    def test_issue_meta_no_cover_disabled(self):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        success, _ = logic.send_issue_meta(issue)
        self.assertTrue(success)

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'debug')
    def test_issue_meta_with_cover_disabled(self, debug_mock):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        svg_data = """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="50"></circle>
            </svg>
        """
        svg_file = SimpleUploadedFile(
            "file.svg",
            svg_data.encode("utf-8"),
        )
        issue.cover_image = svg_file
        issue.save()

        success, msg = logic.send_issue_meta(issue)
        self.assertTrue(success)
        debug_mock.assert_called_once_with(msg)

    def test_issue_cover_bad_issue(self):
        issue = helpers.create_issue(self.journal, articles=[self.article], number="1-2")
        svg_data = """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="50"></circle>
            </svg>
        """
        svg_file = SimpleUploadedFile(
            "file.svg",
            svg_data.encode("utf-8"),
        )
        issue.cover_image = svg_file
        issue.save()

        success, msg = logic.send_issue_meta(issue)
        self.assertFalse(success)
        self.assertEqual(msg, "Cannot upload cover images for non-integer issue number 1-2")

    @mock.patch('plugins.eschol.logic.send_article',
                return_value=None,
                side_effect=Exception('Boom!'))
    def test_article_unexpected_error(self, mock_send):
        _issue = helpers.create_issue(self.journal, articles=[self.article])
        apub = logic.article_to_eschol(article=self.article)
        mock_send.assert_called_once_with(self.article, False, None)
        self.assertFalse(apub.success)
        error_text = f"An unexpected error occured when sending {self.article} " + \
                        "to eScholarship: Boom!"
        self.assertEqual(apub.result, error_text)

    @mock.patch('plugins.eschol.logic.send_issue_meta',
                return_value=None,
                side_effect=Exception('Boom!'))
    def test_issue_unexpected_error(self, mock_send):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        apub = logic.issue_to_eschol(issue=issue)
        mock_send.assert_called_once_with(issue, False)
        self.assertFalse(apub.success)
        error_text = f"An unexpected error occured when sending {issue} to eScholarship: Boom!"
        self.assertEqual(apub.result, error_text)

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'info')
    def test_article_error(self, info_mock):
        apub = logic.article_error(self.article, None, "Boom!")
        self.assertEqual(apub.article, self.article)
        self.assertFalse(apub.success)
        self.assertEqual(apub.result, "Boom!")
        info_mock.assert_called_once_with("Boom!")

    @override_settings(ESCHOL_API_URL="test")
    @mock.patch('plugins.eschol.logic.send_to_eschol')
    def test_provisional_id(self, mock_send):
        result_json = {'data': {'mintProvisionalID': {'id': 'ark:/13030/qtAAAAAAAA'}}}
        mock_send.return_value = Response(json.dumps(result_json))
        ark = logic.get_provisional_id(self.article)
        self.assertEqual(ark, "ark:/13030/qtAAAAAAAA")
