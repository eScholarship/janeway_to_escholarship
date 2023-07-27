from io import StringIO
import os

from django.core.management import call_command
from django.test import TestCase

from utils.testing import helpers
from utils.models import LogEntry

from plugins.eschol.models import EscholArticle
from identifiers.models import Identifier

LOG_ENTRY1 = """Article {} imported by Journal Transporter.

Import metadata:
{{"imported_at": "2023-03-27 06:56:17.753986", "external_identifiers": [{{"name": "source_id", "value": "100"}}], "journal_transporter_article_uuid": "00000000-0000-0000-0000-000000000000"}}
"""

LOG_ENTRY2 = """Article {} imported by Journal Transporter.

Import metadata:
{{"imported_at": "2023-03-27 06:56:17.753986", "external_identifiers": [{{"name": "source_id", "value": "100"}}, {{"name": "ark", "value": "qt00000003"}}], "journal_transporter_article_uuid": "00000000-0000-0000-0000-000000000000"}}
"""

class TestImportArks(TestCase):

    def setUp(self):
        self.journal, _ = helpers.create_journals()
        self.article = helpers.create_article(self.journal)

    def create_log_entry(self, desc):
        self.log_entry = LogEntry.add_entry([], desc.format(self.article.pk), "info", None, target=self.article, subject="Import")
        self.log_entry.save()

    def get_file_path(self, filename):
        return f'{os.path.dirname(__file__)}/test_files/{filename}'

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "add_arks",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    def test_match_source_id_to_external_id(self):
        self.create_log_entry(LOG_ENTRY1)
        out = self.call_command(self.journal.code, self.get_file_path("test1.tsv"))
        self.assertEqual(EscholArticle.objects.count(), 1)
        a = EscholArticle.objects.get(article=self.article)
        self.assertEqual(a.ark, "ark:/13030/qt00000001")
        self.assertEqual(a.source_name, "ojs")
        self.assertEqual(Identifier.objects.count(), 1)
        i = Identifier.objects.get(article=self.article)
        self.assertEqual(i.identifier, "10.00000/C40001")

    def test_match_source_id_to_local_id(self):
        self.create_log_entry(LOG_ENTRY1)
        out = self.call_command(self.journal.code, self.get_file_path("test2.tsv"))
        self.assertEqual(EscholArticle.objects.count(), 1)
        a = EscholArticle.objects.get(article=self.article)
        self.assertEqual(a.ark, "ark:/13030/qt00000002")
        self.assertEqual(a.source_name, "bepress")
        self.assertEqual(Identifier.objects.count(), 1)
        i = Identifier.objects.get(article=self.article)
        self.assertEqual(i.identifier, "10.00000/C40002")

    def test_ark_from_log_entry(self):
        self.create_log_entry(LOG_ENTRY2)
        out = self.call_command(self.journal.code, self.get_file_path("test3.tsv"))
        self.assertEqual(EscholArticle.objects.count(), 1)
        a = EscholArticle.objects.get(article=self.article)
        self.assertEqual(a.ark, "ark:/13030/qt00000003")
        self.assertEqual(a.source_name, "bepress")
        self.assertEqual(Identifier.objects.count(), 1)
        i = Identifier.objects.get(article=self.article)
        self.assertEqual(i.identifier, "10.00000/C40003")


