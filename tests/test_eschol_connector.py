from django.test import TestCase, override_settings
from django.conf import settings
from unittest.mock import patch

from utils.testing import helpers
from django.core.files.uploadedfile import SimpleUploadedFile

from datetime import datetime
from django.utils import timezone

import utils

from submission.models import STAGE_PUBLISHED, Licence, Keyword, Funder, Field, FieldAnswer

#from django.core.management import call_command
#from django.contrib.messages import get_messages

from eschol.logic import *

# TODO:
# - HTML
# - Plural section
# - invalid license
# - Supp Files & galley

class EscholConnectorTest(TestCase):

    def setUp(self):
        # unconfigure ESCHOL API to start
        del settings.ESCHOL_API_URL

        # we need to install the plugin else the reverse call
        # to get the download file link will fail
        #call_command('install_plugins', 'eschol')
        self.user = helpers.create_user("user1@test.edu")
        self.press = helpers.create_press()
        self.journal, _ = helpers.create_journals()
        self.article = helpers.create_article(self.journal,
                                              with_author=False,
                                              date_published=datetime(2023, 1, 1, tzinfo=timezone.get_current_timezone()),
                                              stage=STAGE_PUBLISHED,
                                              language=None)
        self.article.owner = self.user
        self.article.save()

    def test_data_availability(self):
        field1 = Field.objects.create(journal=self.journal, press=self.press, name="Data Availability", kind="text", order=1, required=False)
        answer1 = FieldAnswer.objects.create(field=field1, article=self.article, answer="Public repository")

        field2 = Field.objects.create(journal=self.journal, press=self.press, name="Data URL", kind="text", order=2, required=False)
        answer2 = FieldAnswer.objects.create(field=field2, article=self.article, answer="http://data.repo")

        j, e = get_article_json(self.article, get_unit(self.journal))

        self.assertEqual(j["dataAvailability"], "publicRepo")
        self.assertEqual(j["dataURL"], "http://data.repo")

    def test_minimal_json(self):
        j, e = get_article_json(self.article, get_unit(self.journal))
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
        license, _ = Licence.objects.get_or_create(journal=self.journal,
                                                   press=self.press,
                                                   name="Creative Commons 4",
                                                   short_name="CC4",
                                                   url="https://creativecommons.org/licenses/by/4.0")
        license.save()
        author = helpers.create_author(self.journal)
        funder, _ = Funder.objects.get_or_create(name="Test Funder", fundref_id="http://dx.doi.org/10.13039/501100021082")
        funder.save()

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
        self.article.funders.add(funder)

        self.article.save()
        author.snapshot_self(self.article)

        self.journal.issn = "1111-1111"
        self.journal.save()

        j, e = get_article_json(self.article, get_unit(self.journal))
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
        self.assertEqual(j["orderInSection"], 10001)
        self.assertEqual(len(j["localIDs"]), 1)
        self.assertEqual(j["localIDs"][0]["id"], f'janeway_{self.article.pk}')
        self.assertEqual(len(j["authors"]), 1)
        self.assertEqual(j["authors"][0]['nameParts']['fname'], "Author")
        self.assertEqual(j["authors"][0]['nameParts']['lname'], "User")
        self.assertEqual(j["authors"][0]['nameParts']['institution'], "Author institution")
        self.assertEqual(j["authors"][0]['nameParts']['mname'], "A")
        self.assertEqual(j["authors"][0]['email'], "authoruser@martineve.com")
        self.assertEqual(len(j["grants"]), 1)
        self.assertEqual(j["grants"][0]["name"], "Test Funder")
        self.assertEqual(j["grants"][0]["reference"], "http://dx.doi.org/10.13039/501100021082")

        self.assertEqual(len(j), 32)



    @patch.object(utils.logger.PrefixedLoggerAdapter, 'error')
    def test_send_article_no_issue(self, error_mock):
        epub, error = send_article(self.article, False, None)
        msg = f'{self.article} published without issue'
        self.assertEqual(error, msg)
        error_mock.assert_called_once_with(msg)

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'debug')
    def test_article_to_eschol(self, debug_mock):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        self.article.primary_issue = issue
        self.article.issues.add(issue)
        self.article.save()
        epub, error = article_to_eschol(article=self.article)
        debug_mock.assert_called_once_with("Escholarhip Deposit for Article 1: {'item': {'sourceName': 'janeway', 'sourceID': '1', 'sourceURL': 'localhost', 'submitterEmail': 'user1@test.edu', 'title': 'Test Article from Utils Testing Helpers', 'type': 'ARTICLE', 'published': '2023-01-01', 'isPeerReviewed': True, 'contentVersion': 'PUBLISHER_VERSION', 'journal': 'Journal One', 'units': ['TST'], 'pubRelation': 'EXTERNAL_PUB', 'datePublished': '2023-01-01', 'sectionHeader': 'Article', 'volume': '0', 'issue': '0', 'issueTitle': 'Test Issue from Utils Testing Helpers', 'issueDate': '2022-01-01', 'orderInSection': 10001, 'localIDs': [{'id': '/TST.1', 'scheme': 'DOI'}, {'id': 'janeway_1', 'scheme': 'OTHER_ID', 'subScheme': 'other'}]}}")

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'debug')
    def test_issue_to_eschol(self, debug_mock):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        objs, errors = issue_to_eschol(issue=issue)
        debug_mock.assert_called_once_with(f"Escholarhip Deposit for Article {self.article.pk}: {{'item': {{'sourceName': 'janeway', 'sourceID': '{self.article.pk}', 'sourceURL': 'localhost', 'submitterEmail': 'user1@test.edu', 'title': 'Test Article from Utils Testing Helpers', 'type': 'ARTICLE', 'published': '2023-01-01', 'isPeerReviewed': True, 'contentVersion': 'PUBLISHER_VERSION', 'journal': 'Journal One', 'units': ['TST'], 'pubRelation': 'EXTERNAL_PUB', 'datePublished': '2023-01-01', 'sectionHeader': 'Article', 'volume': '0', 'issue': '0', 'issueTitle': 'Test Issue from Utils Testing Helpers', 'issueDate': '2022-01-01', 'orderInSection': 10001, 'localIDs': [{{'id': '/TST.{self.article.pk}', 'scheme': 'DOI'}}, {{'id': 'janeway_{self.article.pk}', 'scheme': 'OTHER_ID', 'subScheme': 'other'}}]}}}}")

    @patch.object(utils.logger.PrefixedLoggerAdapter, 'info')
    def test_is_not_configured(self, info_mock):
        self.assertFalse(is_configured())
        info_mock.assert_called_once_with("Escholarship API not configured.")

    @override_settings(ESCHOL_API_URL="test")
    def test_is_configured(self):
        self.assertTrue(is_configured())

    def test_issue_meta_no_cover(self):
        issue = helpers.create_issue(self.journal, articles=[self.article])
        success, msg = send_issue_meta(issue)
        self.assertTrue(success)
        self.assertTrue(msg, "No cover image")

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

        success, msg = send_issue_meta(issue)
        self.assertTrue(success)
        debug_mock.assert_called_once_with(msg)

    def test_article_unexpected_error(self):
        # pass a non-article so we know it'll generate an unexpected error
        epub, error = article_to_eschol(article=self.journal)
        self.assertEqual(error, f"An unexpected error occured when sending {self.journal} to eScholarship: 'Journal' object has no attribute 'journal'")

    def test_issue_unexpected_error(self):
        # pass a non-issue so we know it'll generate an unexpected error
        epub, errors = issue_to_eschol(issue=self.journal)
        self.assertEqual(errors[0], f"An unexpected error occured when sending {self.journal} to eScholarship: 'Journal' object has no attribute 'cover_image'")