from django.test import TestCase

from utils.testing import helpers
from django.core.files.uploadedfile import SimpleUploadedFile

from datetime import datetime
from django.utils import timezone

from django.core.management import call_command

from eschol.logic import get_article_json, get_unit

class EscholConnectorTest(TestCase):

    def setUp(self):
        # we need to install the plugin else the reverse call
        # to get the download file link will fail
        call_command('install_plugins', 'eschol')
        self.user = helpers.create_user("user1@test.edu")
        self.request = helpers.Request()
        self.request.user = self.user
        
        self.press = helpers.create_press()
        self.journal, _ = helpers.create_journals()
        self.article_in_production = helpers.create_article(self.journal, 
                                                            with_author=False, 
                                                            date_published=datetime(2023, 1, 1, tzinfo=timezone.get_current_timezone()),
                                                            language=None)
        self.article_in_production.owner = self.user
        self.article_in_production.save()
        self.test_pdf = SimpleUploadedFile("test.pdf", b"\x00\x01\x02\x03")
        self.files = []
        self.file = helpers.create_test_file(self, self.test_pdf)[0]
        self.galley = helpers.create_galley(self.article_in_production, file_obj=self.file)

    def test_minimal_info(self):
        j, e = get_article_json(self.article_in_production, get_unit(self.journal))
        self.assertEqual(j["sourceName"], "janeway")
        self.assertEqual(j["sourceID"], str(self.article_in_production.pk))
        self.assertEqual(j["sourceURL"], self.press.domain)
        self.assertEqual(j["submitterEmail"], self.user.email)
        self.assertEqual(j["title"], self.article_in_production.title)        
        self.assertEqual(j["type"], "ARTICLE")
        self.assertEqual(j["published"], self.article_in_production.date_published.strftime("%Y-%m-%d"))
        self.assertEqual(j["datePublished"], self.article_in_production.date_published.strftime("%Y-%m-%d"))
        self.assertEqual(j["isPeerReviewed"], self.article_in_production.peer_reviewed)
        self.assertEqual(j["contentVersion"], "PUBLISHER_VERSION")
        self.assertEqual(j["journal"], self.journal.name)
        self.assertEqual(len(j["units"]), 1)
        self.assertEqual(j["units"][0], self.journal.code)
        self.assertEqual(j["pubRelation"], "EXTERNAL_PUB")
        self.assertIn("http://localhost/TST/plugins/eschol/download/1/file/1/?access=", j["contentLink"])
        self.assertEqual(j["contentFileName"], "test.pdf")
        self.assertEqual(len(j["localIDs"]), 1)
        self.assertEqual(j["localIDs"][0]["id"], f'janeway_{self.article_in_production.pk}')
        # TODO: this will change if we require or not section
        self.assertEqual(len(j), 17)
