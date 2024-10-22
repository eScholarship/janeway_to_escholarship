from datetime import datetime
import mock
from django.utils import timezone
from django.conf import settings

from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from utils.testing import helpers
from journal.tests.utils import make_test_journal

from core.models import File
from core.files import save_file
from submission.models import STAGE_PUBLISHED

from plugins.eschol.models import (AccessToken,
                                   ArticlePublicationHistory,
                                   IssuePublicationHistory)
from plugins.eschol.views import publish_issue_task

TEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD v1.2 20120330//EN" "http://jats.nlm.nih.gov/publishing/1.2/JATS-journalpublishing1.dtd">
<article>test</article>
"""

class TestViews(TestCase):

    def setUp(self):
        # unconfigure ESCHOL API to start
        del settings.ESCHOL_API_URL

        self.press = helpers.create_press()

        journal_kwargs = {'code': "fetests",
                          'domain': "fetests.janeway.systems",}
        self.journal = make_test_journal(**journal_kwargs)
        d = datetime(2023, 1, 1, tzinfo=timezone.get_current_timezone())
        self.article = helpers.create_article(self.journal,
                                              with_author=False,
                                              date_published=d,
                                              stage=STAGE_PUBLISHED,
                                              language=None)

        self.admin_user = helpers.create_user("adminuser@martineve.com")
        self.admin_user.is_staff = True
        self.admin_user.is_active = True
        self.admin_user.save()

        self.article.owner = self.admin_user
        self.article.save()

        self.issue = helpers.create_issue(self.journal, articles=[self.article])

        self.request = helpers.Request()
        self.request.user = self.admin_user

    def create_file(self, article, file, label):
        path_parts = ('articles', article.pk)

        return save_file(self.request, file, label=label, public=True, path_parts=path_parts,)

    def login_redirect(self, url):
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], f"/login/?next={url}")

    @mock.patch('plugins.eschol.logic.send_article')
    def test_publish_issue_task(self, mock_send):
        mock_send.return_value = ArticlePublicationHistory.objects.create(article=self.article,
                                                                          success=True)
        result = publish_issue_task(self.issue.pk)
        self.assertEqual(IssuePublicationHistory.objects.filter(issue=self.issue).count(), 1)
        ipub = IssuePublicationHistory.objects.get(issue=self.issue)
        self.assertTrue(ipub.success)
        self.assertTrue(ipub.is_complete)
        msg = f"{self.issue} publication successful on {ipub.date}: 1 of 1 articles published."
        self.assertEqual(result, msg)

    # not sure how to get the settings right to make this work in test env
    # @override_settings(URL_CONFIG="domain")
    # def test_publish_issue(self):
    #     url = reverse('eschol_publish_issue', kwargs={'issue_id': self.issue.pk})
    #     self.login_redirect(url)

    #     self.client.force_login(self.admin_user)
    #     response = self.client.get(url, SERVER_NAME=self.journal.domain)
    #     self.assertContains(response, f"Publish request queued for {self.issue}.")

    @mock.patch('plugins.eschol.logic.send_article')
    @override_settings(URL_CONFIG="domain")
    def test_publish_article(self, mock_send):
        url = reverse('eschol_publish_article', kwargs={'article_id': self.article.pk})
        self.login_redirect(url)

        mock_send.return_value = ArticlePublicationHistory.objects.create(article=self.article,
                                                                          success=True)
        self.client.force_login(self.admin_user)
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(ArticlePublicationHistory.objects.filter(article=self.article).count(), 1)
        apub = ArticlePublicationHistory.objects.get(article=self.article)
        self.assertContains(response, f"Published {self.article}")
        self.assertContains(response, str(apub))

    @override_settings(URL_CONFIG="domain")
    def test_list_articles(self):
        url = reverse('eschol_list_articles', kwargs={'issue_id': self.issue.pk})
        self.login_redirect(url)

        self.client.force_login(self.admin_user)
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        i = self.issue
        result = f"Publish Volume {i.volume} Issue {i.issue} {i.issue_title} ({i.date.year})"
        self.assertContains(response, result)

    @override_settings(URL_CONFIG="domain")
    def test_eschol_manager(self):
        url = reverse('eschol_manager')
        self.login_redirect(url)

        self.client.force_login(self.admin_user)
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertContains(response, "Publish Issues")

    @override_settings(URL_CONFIG="domain")
    def test_access_file(self):
        f = SimpleUploadedFile(
            "test.pdf",
            b"\x00\x01\x02\x03",
        )
        tf = self.create_file(self.article, f, "Test File 1")
        t = AccessToken.objects.create(token="abc", article_id=self.article.pk, file_id=tf.pk)
        url = reverse('access_article_file', kwargs={'article_id': self.article.pk,
                                                     'file_id': tf.pk}) + f"?access={t.token}"
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(response.status_code, 200)

    def test_access_file_file_missing(self):
        f = File.objects.create(article_id=self.article.pk,
                                label="file",
                                is_galley=True,
                                original_filename="test.pdf",
                                mime_type="application/pdf",
                                uuid_filename="uuid.pdf")
        t = AccessToken.objects.create(token="abc", article_id=self.article.pk, file_id=f.pk)
        url = reverse('access_article_file', kwargs={'article_id': self.article.pk,
                                                     'file_id': f.pk}) + f"?access={t.token}"
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(response.status_code, 404)

    def test_access_file_no_file_id(self):
        f = SimpleUploadedFile(
            "test.pdf",
            b"\x00\x01\x02\x03",
        )
        tf = self.create_file(self.article, f, "Test File 1")
        t = AccessToken.objects.create(token="abc", article_id=self.article.pk, file_id=tf.pk)

        url = "/plugins/escholarship-publishing-plugin/download/" + \
                f"{self.article.pk}/file//?access={t.token}"
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(response.status_code, 404)

    def test_access_file_no_token(self):
        f = SimpleUploadedFile(
            "test.pdf",
            b"\x00\x01\x02\x03",
        )
        tf = self.create_file(self.article, f, "Test File 1")
        t = AccessToken.objects.create(token="abc", article_id=self.article.pk, file_id=tf.pk + 1)
        url = reverse('access_article_file', kwargs={'article_id': self.article.pk,
                                                     'file_id': tf.pk}) + f"?access={t.token}"
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(response.status_code, 403)

    def test_access_file_no_file_obj(self):
        f = SimpleUploadedFile(
            "test.pdf",
            b"\x00\x01\x02\x03",
        )
        tf = self.create_file(self.article, f, "Test File 1")
        t = AccessToken.objects.create(token="abc", article_id=self.article.pk, file_id=tf.pk + 1)

        url = reverse('access_article_file', kwargs={'article_id': self.article.pk,
                                                     'file_id': tf.pk + 1}) + f"?access={t.token}"
        response = self.client.get(url, SERVER_NAME=self.journal.domain)
        self.assertEqual(response.status_code, 404)
