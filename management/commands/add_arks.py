from django.core.management.base import BaseCommand, CommandError

import json, csv

from utils.models import LogEntry
from journal.models import Journal
from submission.models import Article
from django.contrib.contenttypes.models import ContentType

from plugins.eschol.models import EscholArticle
from identifiers.models import Identifier

# The following query to the jschol db will create the expected input file
# "SELECT arks.id, arks.source, external_id, items.attrs->>'$.doi' as doi FROM arks LEFT JOIN unit_items ON arks.id = unit_items.item_id LEFT JOIN items ON items.id = arks.id  WHERE unit_id = '<journal-code>';"

class Command(BaseCommand):
    """Adds EscholArticle objects with arks for items imported from OJS for a given journal"""
    help = "Adds EscholArticle objects for items imported from OJS for a given journal"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to add arks", type=str
        )
        parser.add_argument(
            "import_file", help="path to an export file containing the ojs ids and arks", type=str
        )

    def handle(self, *args, **options):
        # janeway journal codes are limited to 24 chars
        # truncate it if the user doesn't
        journal_code = options.get("journal_code")[:24]
        import_file = options.get("import_file")

        if not Journal.objects.filter(code=journal_code).exists():
            raise CommandError(f'Journal does not exist {journal_code}')

        j = Journal.objects.get(code=journal_code)

        # map ojs_id to ark, source and doi
        id_map = {}
        # map arks to source and doi
        # (just in case we have no ojs id but we have an ark in a log entry)
        ark_map = {}
        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter="\t")
            for r in reader:
                ojs_id = None
                # if source is ojs 'external_id' should match
                # source_id in janeway log entry
                if r["source"] == "ojs":
                    ojs_id = r["external_id"]
                    print(f'use external_id as ojs_id {ojs_id}')
                # if the original source is not ojs we may still have a local_id
                # that includes the ojs id
                elif "local_ids" in r and r["local_ids"] and not r["local_ids"]  == "NULL":
                    local_ids = json.loads(r["local_ids"])
                    for x in local_ids:
                        # unfortunately the local id that contains
                        # the ojs id has type 'None' so see if it
                        # matches the pattern
                        prefix = f'{journal_code}_'
                        if x["id"].startswith(prefix):
                            ojs_id = x["id"][len(prefix):]
                            print(f'use local_id as ojs_id {ojs_id}')
                if ojs_id:
                    id_map[ojs_id] = {"ark": r["id"], "source": r["source"], "external_id": r["external_id"], "doi": r["doi"]}
                    print(f'add {ojs_id}: {id_map[ojs_id]}')

                ark_map[r["id"]]  = {"source": r["source"], "external_id": r["external_id"], "doi": r["doi"]}

        ctype = ContentType.objects.get(app_label='submission', model='article')

        for a in j.article_set.all():
            ark = None
            desc = f'Article {a.pk} imported by Journal Transporter.'
            e = LogEntry.objects.filter(content_type=ctype, object_id=a.pk, description__startswith=desc)
            if e.count() > 1:
                print(f'ERROR Article {a.pk}: multiple log entries found')
            elif e.count() < 1:
                print(f'ERROR Article {a.pk}: no log entries found')
            else:
                d = json.loads(e[0].description.partition("Import metadata:")[2])

                for i in d['external_identifiers']:
                    # source_id is the ojs id
                    if i['name'] == "source_id":
                        ojs_id = i['value']
                        print(f'parsed ojs id = {ojs_id}')
                    # some items also logged an ark upon import
                    if i['name'] == "ark":
                        ark = i["value"]

                ojs_item = id_map.get(ojs_id, False)
                if ojs_item:
                    ark = ojs_item["ark"]
                    source = ojs_item["source"]
                    source_id = ojs_item["external_id"]
                    doi = ojs_item["doi"]
                elif ark:
                    ark_item = ark_map.get(ark, False)
                    if ark_item:
                        source = ark_item["source"]
                        source_id = ark_item["external_id"]
                        doi = ark_item["doi"]

                if ark:
                    ark = f'ark:/13030/{ark}'
                    e, created = EscholArticle.objects.get_or_create(article=a, ark=ark,
                                                                     defaults={'source_name': source,
                                                                               'source_id': source_id})
                    if not created and (e.source != source or e.source_id != source_id):
                        print(f'ERROR: {ark} found with different sources {source} and {e.source_name}')

                    if doi and not doi == 'NULL':
                        # If we have an DOI delete any existing DOIs
                        # We assume the DOI coming from the jschol export is the most recent
                        if Identifier.objects.filter(article=a, id_type='doi').exists():
                            Identifier.objects.filter(article=a, id_type='doi').delete()
                        doi_options = {
                            'id_type': 'doi',
                            'identifier': doi,
                            'article': a
                        }

                        doi = Identifier.objects.create(**doi_options)
                        e.is_doi_registered = True
                        e.save()
                        print(f'Added doi {doi}')
                else:
                    if a.stage == 'Published':
                        print(f'ERROR Published article {a.pk}: OJS id not found in export')

        print("Ark and DOI import complete.")

        ids = EscholArticle.objects.filter(article__journal__code=journal_code).values_list('article__pk', flat=True)
        articles = Article.objects.filter(journal__code=journal_code, stage="Published").exclude(pk__in=ids)
        if articles.count() == 0:
            print(f"There are no published articles in {journal_code} without an escholarship ark assigned")
        else:
            print(f"The following published articles don't have an ark assigned:")
            for a in articles:
                print(f'{a.stage}\t{a.pk}\t{a.url}')
