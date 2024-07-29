from django.test import TestCase, override_settings
from django.conf import settings
from unittest.mock import patch

from utils.testing import helpers
from django.core.files.uploadedfile import SimpleUploadedFile

from datetime import datetime
from django.utils import timezone

import utils, os

from submission.models import STAGE_PUBLISHED, Licence, Keyword, Field, FieldAnswer
from core.models import File, SupplementaryFile
from core.files import save_file
from submission.models import FrozenAuthor

# these imports are needed to make sure plugin urls are loaded
from core import models as core_models, urls

import plugins.eschol.logic as logic
from plugins.eschol.models import EscholArticle

import mock

class EscholConnectorTest(TestCase):

    def setUp(self):
        # unconfigure ESCHOL API to start
        del settings.ESCHOL_API_URL

        self.user = helpers.create_user("user1@test.edu")
        self.request = helpers.Request()
        self.request.user = self.user
        self.press = helpers.create_press()
        self.journal, _ = helpers.create_journals()
        self.article = helpers.create_article(self.journal,
                                              with_author=False,
                                              date_published=datetime(2023, 1, 1, tzinfo=timezone.get_current_timezone()),
                                              stage=STAGE_PUBLISHED,
                                              language=None)
        self.article.owner = self.user
        self.article.save()

    def create_file(self, article, file, label):
        path_parts = ('articles', article.pk)

        return save_file(self.request, file, label=label, public=True, path_parts=path_parts,)

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

        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertEqual(j['id'], 'ark:/13030/qtXXXXXXXX')
        self.assertIn(f"http://localhost/TST/plugins/escholarship-publishing-plugin/download/{self.article.pk}/file/", j["contentLink"])
        self.assertEqual(j["contentFileName"], 'qtXXXXXXXX.html')

        self.assertEqual(len(j['suppFiles']), 2)

        self.assertEqual(j['suppFiles'][0]['file'], 'qtXXXXXXXX.xml')
        self.assertEqual(j['suppFiles'][0]['contentType'], 'application/xml')
        self.assertEqual(j['suppFiles'][0]['size'], 157291)
        self.assertIn(f"http://localhost/TST/plugins/escholarship-publishing-plugin/download/{self.article.pk}/file/{xml_obj.pk}/?access=", j['suppFiles'][0]['fetchLink'])
        self.assertEqual(j['suppFiles'][0]['title'], '[XML] Test Article from Utils Testing Helpers')

        self.assertEqual(j['suppFiles'][1]['file'], 'test.pdf')
        self.assertEqual(j['suppFiles'][1]['contentType'], 'application/pdf')
        self.assertEqual(j['suppFiles'][1]['size'], 4)
        self.assertIn(f"http://localhost/TST/plugins/escholarship-publishing-plugin/download/{self.article.pk}/file/{pdf_obj.pk}/?access=", j['suppFiles'][1]['fetchLink'])
        #self.assertEqual(j['suppFiles'][1]['title'], '')

        self.assertEqual(len(j['imgFiles']), 1)
        self.assertEqual(j['imgFiles'][0]['file'], 'test.png')
        self.assertIn(f"http://localhost/TST/plugins/escholarship-publishing-plugin/download/{self.article.pk}/file/{img_obj.pk}/?access=", j['imgFiles'][0]['fetchLink'])

    def test_galley(self):

        f = File.objects.create(article_id=self.article.pk, label="file", is_galley=True, original_filename="test.pdf", mime_type="application/pdf", uuid_filename="uuid.pdf")
        galley = helpers.create_galley(self.article, file_obj=f)

        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertIn(f"http://localhost/TST/plugins/escholarship-publishing-plugin/download/{self.article.pk}/file/{f.pk}/?access=", j["contentLink"])
        self.assertEqual(j["contentFileName"], "test.pdf")

    def test_supp_files(self):
        f1 = SimpleUploadedFile(
            "test.pdf",
            b"\x00\x01\x02\x03",
        )
        tf1 = self.create_file(self.article, f1, "Test File 1")

        f2 = SimpleUploadedFile(
            "test.xml",
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD v1.2 20120330//EN" "http://jats.nlm.nih.gov/publishing/1.2/JATS-journalpublishing1.dtd">
            <article>test</article>
            """.strip().encode("utf-8"),
        )
        tf2 = self.create_file(self.article, f2, "Test File 2")

        sf1 = SupplementaryFile.objects.create(file=tf1)
        self.article.supplementary_files.add(sf1)

        sf2 = SupplementaryFile.objects.create(file=tf2)
        self.article.supplementary_files.add(sf2)

        self.article.save()

        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertEqual(len(j['suppFiles']), 2)

        self.assertEqual(j['suppFiles'][0]['file'], 'test.pdf')
        self.assertEqual(j['suppFiles'][0]['contentType'], 'application/pdf')
        self.assertEqual(j['suppFiles'][0]['size'], 4)
        self.assertIn(f"http://localhost/TST/plugins/escholarship-publishing-plugin/download/{self.article.pk}/file/{tf1.pk}/?access=", j['suppFiles'][0]['fetchLink'])

        self.assertEqual(j['suppFiles'][1]['file'], 'test.xml')
        self.assertEqual(j['suppFiles'][1]['contentType'], 'application/xml')
        self.assertEqual(j['suppFiles'][1]['size'], 250)
        self.assertIn(f"http://localhost/TST/plugins/escholarship-publishing-plugin/download/{self.article.pk}/file/{tf2.pk}/?access=", j['suppFiles'][1]['fetchLink'])


    def test_invalid_license(self):
        license, _ = Licence.objects.get_or_create(journal=self.journal,
                                                   press=self.press,
                                                   name="Creative Commons 4",
                                                   short_name="CC4",
                                                   url="https://bad.url")
        license.save()
        self.article.license = license
        self.article.save()

        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertNotIn("license", j)


    def test_data_availability(self):
        field1 = Field.objects.create(journal=self.journal, press=self.press, name="Data Availability", kind="text", order=1, required=False)
        answer1 = FieldAnswer.objects.create(field=field1, article=self.article, answer="Public repository")

        field2 = Field.objects.create(journal=self.journal, press=self.press, name="Data URL", kind="text", order=2, required=False)
        answer2 = FieldAnswer.objects.create(field=field2, article=self.article, answer="http://data.repo")

        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))

        self.assertEqual(j["dataAvailability"], "publicRepo")
        self.assertEqual(j["dataURL"], "http://data.repo")

    def test_plural_sections(self):
        article2 = helpers.create_article(self.journal,
                                          with_author=False,
                                          date_published=datetime(2023, 1, 1, tzinfo=timezone.get_current_timezone()))

        issue = helpers.create_issue(self.journal, articles=[self.article, article2])

        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))
        self.assertEqual(j["sectionHeader"], "Articles")

    def test_minimal_json(self):
        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))
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
        self.assertEqual(len(j), 15)

    def test_kitchen_sink(self):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        issue.issue_description = "Test issue description<br>"
        issue.save()
        license, _ = Licence.objects.get_or_create(journal=self.journal,
                                                   press=self.press,
                                                   name="Creative Commons 4",
                                                   short_name="CC4",
                                                   url="https://creativecommons.org/licenses/by/4.0")
        license.save()
        author = helpers.create_author(self.journal)
        corporate_author  = FrozenAuthor.objects.create(article=self.article, institution="Author Collective", is_corporate=True, order=2)
        #funder, _ = Funder.objects.get_or_create(name="Test Funder", fundref_id="http://dx.doi.org/10.13039/501100021082")
        #funder.save()

        self.article.abstract = "This is the abstract"
        self.article.date_submitted = datetime(2022, 1, 1, tzinfo=timezone.get_current_timezone())
        self.article.date_accepted = datetime(2022, 2, 2, tzinfo=timezone.get_current_timezone())
        self.article.custom_how_to_cite = "Citation, blah. 2023"
        self.article.first_page = 1
        self.article.last_page = 2
        self.article.language = "eng"
        self.article.publisher_name = "The Publisher Name"
        self.article.keywords.add(Keyword.objects.create(word="keyword1"))
        self.article.license = license
        self.article.authors.add(author)
        #self.article.funders.add(funder)

        self.article.save()
        author.snapshot_self(self.article)

        self.journal.issn = "1111-1111"
        self.journal.save()

        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))
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
        self.assertEqual(len(j["localIDs"]), 1)
        self.assertEqual(j["localIDs"][0]["id"], f'janeway_{self.article.pk}')
        self.assertEqual(len(j["authors"]), 2)
        self.assertEqual(j["authors"][0]['nameParts']['fname'], "Author")
        self.assertEqual(j["authors"][0]['nameParts']['lname'], "User")
        self.assertEqual(j["authors"][0]['nameParts']['institution'], "Author institution")
        self.assertEqual(j["authors"][0]['nameParts']['mname'], "A")
        self.assertEqual(j["authors"][0]['email'], "authoruser@martineve.com")
        self.assertEqual(j["authors"][1]['nameParts']['organization'], "Author Collective")
        #self.assertEqual(len(j["grants"]), 1)
        #self.assertEqual(j["grants"][0]["name"], "Test Funder")
        #self.assertEqual(j["grants"][0]["reference"], "http://dx.doi.org/10.13039/501100021082")

        self.assertEqual(len(j), 32)

    def test_ojs_source(self):
        EscholArticle.objects.create(article=self.article, ark="qt0000000", source_name="ojs", source_id="555555")
        j, e = logic.get_article_json(self.article, logic.get_unit(self.journal))
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

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'debug')
    def test_article_to_eschol(self, debug_mock):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        self.article.primary_issue = issue
        self.article.issues.add(issue)
        self.article.save()
        apub = logic.article_to_eschol(article=self.article)
        debug_mock.assert_called_once_with(f"Escholarhip Deposit for Article {self.article.pk}: {{'item': {{'sourceName': 'janeway', 'sourceID': '{self.article.pk}', 'sourceURL': 'localhost', 'submitterEmail': 'user1@test.edu', 'title': 'Test Article from Utils Testing Helpers', 'type': 'ARTICLE', 'published': '2023-01-01', 'isPeerReviewed': True, 'contentVersion': 'PUBLISHER_VERSION', 'journal': 'Journal One', 'units': ['TST'], 'pubRelation': 'EXTERNAL_PUB', 'datePublished': '2023-01-01', 'sectionHeader': 'Article', 'volume': '0', 'issue': '0', 'issueTitle': 'Test Issue from Utils Testing Helpers', 'issueDate': '2022-01-01', 'orderInSection': 10001, 'localIDs': [{{'id': 'janeway_{self.article.pk}', 'scheme': 'OTHER_ID', 'subScheme': 'other'}}]}}}}")

    def test_private_render_galley(self):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        f = File.objects.create(article_id=self.article.pk, label="file", is_galley=True, original_filename="test.pdf", mime_type="application/pdf", uuid_filename="uuid.pdf")
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
        self.assertTrue(ipub.success)
        self.assertEqual(ipub.articlepublicationhistory_set.all().count(), 1)
        debug_mock.assert_called_once_with(f"Escholarhip Deposit for Article {self.article.pk}: {{'item': {{'sourceName': 'janeway', 'sourceID': '{self.article.pk}', 'sourceURL': 'localhost', 'submitterEmail': 'user1@test.edu', 'title': 'Test Article from Utils Testing Helpers', 'type': 'ARTICLE', 'published': '2023-01-01', 'isPeerReviewed': True, 'contentVersion': 'PUBLISHER_VERSION', 'journal': 'Journal One', 'units': ['TST'], 'pubRelation': 'EXTERNAL_PUB', 'datePublished': '2023-01-01', 'sectionHeader': 'Article', 'volume': '0', 'issue': '0', 'issueTitle': 'Test Issue from Utils Testing Helpers', 'issueDate': '2022-01-01', 'orderInSection': 10001, 'localIDs': [{{'id': 'janeway_{self.article.pk}', 'scheme': 'OTHER_ID', 'subScheme': 'other'}}]}}}}")

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'info')
    def test_is_not_configured(self, info_mock):
        self.assertFalse(logic.is_configured())
        info_mock.assert_called_once_with("Escholarship API not configured.")

    @override_settings(ESCHOL_API_URL="test")
    def test_is_configured(self):
        self.assertTrue(logic.is_configured())

    def test_issue_meta_no_cover(self):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        success, msg = logic.send_issue_meta(issue)
        self.assertTrue(success)

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'debug')
    def test_issue_meta_with_cover(self, debug_mock):
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

    @mock.patch('plugins.eschol.logic.send_article', return_value=None, side_effect=Exception('Boom!'))
    def test_article_unexpected_error(self, mock_send):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        apub = logic.article_to_eschol(article=self.article)
        mock_send.assert_called_once_with(self.article, False, None)
        self.assertFalse(apub.success)
        self.assertEqual(apub.result, f"An unexpected error occured when sending {self.article} to eScholarship: Boom!")

    @mock.patch('plugins.eschol.logic.send_issue_meta', return_value=None, side_effect=Exception('Boom!'))
    def test_issue_unexpected_error(self, mock_send):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        apub = logic.issue_to_eschol(issue=issue)
        mock_send.assert_called_once_with(issue, False)
        self.assertFalse(apub.success)
        self.assertEqual(apub.result, f"An unexpected error occured when sending {issue} to eScholarship: Boom!")