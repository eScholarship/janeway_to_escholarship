from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from utils.testing import helpers
from journal.tests.utils import make_test_journal

from core.models import File
from core.files import save_file

from plugins.eschol.models import AccessToken

TEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD v1.2 20120330//EN" "http://jats.nlm.nih.gov/publishing/1.2/JATS-journalpublishing1.dtd">
<article>test</article>
"""

class TestViews(TestCase):

    def setUp(self):
        self.press = helpers.create_press()

        journal_kwargs = {'code': "fetests",
                          'domain': "fetests.janeway.systems",}
        self.journal = make_test_journal(**journal_kwargs)
        self.article = helpers.create_article(self.journal)
        self.issue = helpers.create_issue(self.journal, articles=[self.article])

        self.admin_user = helpers.create_user("adminuser@martineve.com")
        self.admin_user.is_staff = True
        self.admin_user.is_active = True
        self.admin_user.save()

        self.request = helpers.Request()
        self.request.user = self.admin_user

    def create_file(self, article, file, label):
        path_parts = ('articles', article.pk)

        return save_file(self.request, file, label=label, public=True, path_parts=path_parts,)

    @override_settings(URL_CONFIG="domain")
    def test_publish_issue(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('eschol_publish_issue',
                                            kwargs={'issue_id': self.issue.pk}),
                                    SERVER_NAME=self.journal.domain)
        self.assertContains(response, f"Publish request queued for {self.issue}.")

    @override_settings(URL_CONFIG="domain")
    def test_publish_article(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('eschol_publish_article',
                                           kwargs={'article_id': self.article.pk}),
                                    SERVER_NAME=self.journal.domain)
        self.assertContains(response, f"Published {self.article}")

    @override_settings(URL_CONFIG="domain")
    def test_list_articles(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('eschol_list_articles',
                                           kwargs={'issue_id': self.issue.pk}),
                                    SERVER_NAME=self.journal.domain)
        i = self.issue
        result = f"Publish Volume {i.volume} Issue {i.issue} {i.issue_title} ({i.date.year})"
        self.assertContains(response, result)

    @override_settings(URL_CONFIG="domain")
    def test_eschol_manager(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('eschol_manager'), SERVER_NAME=self.journal.domain)
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
