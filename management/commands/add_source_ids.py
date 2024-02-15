from django.core.management.base import BaseCommand, CommandError

from plugins.eschol.models import EscholArticle

import csv

class Command(BaseCommand):
    """Adds source_ids for EscholArticles that have other sources"""
    help = "Adds source_ids for EscholArticles that have other sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to add arks", type=str
        )
        parser.add_argument(
            "import_file", help="path to an export file containing the ojs ids and arks", type=str
        )

    def handle(self, *args, **options):
        code = options.get("journal_code")[:24]
        import_file = options.get("import_file")

        arks = {}
        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter="\t")
            for row in reader:
                arks[row["id"]] = {"source": row["source"], "external_id": row["external_id"]}

        for a in EscholArticle.objects.filter(article__journal__code=code).exclude(source_name=None):
            ark = f"qt{a.get_short_ark()}"
            if ark in arks:
                row = arks[ark]
                if row["source"] == a.source_name:
                    a.source_id = row["external_id"]
                    a.save()
                else:
                    print(f"ERROR: source mismatch {a.article}")
            else:
                print(f"ERROR ark not found {ark} for {a.article}")
