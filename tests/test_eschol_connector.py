from django.test import TestCase, override_settings
from django.conf import settings
from unittest.mock import patch

from utils.testing import helpers
from django.core.files.uploadedfile import SimpleUploadedFile

from datetime import datetime
from django.utils import timezone

import utils

from submission.models import STAGE_PUBLISHED

#from django.core.management import call_command
#from django.contrib.messages import get_messages

from eschol.logic import *

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