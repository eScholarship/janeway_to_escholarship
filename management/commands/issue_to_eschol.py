from django.core.management.base import BaseCommand

from journal.models import Issue
from plugins.eschol import logic
from plugins.eschol.models import EscholArticle

class Command(BaseCommand):
    """ Deposits specified issue in escholarship via graphql api"""
    help = "Deposits specified issue in escholarship via graphql api"

    def add_arguments(self, parser):
        parser.add_argument(
            "issue_id", help="`id` of issue to send to escholarship", type=int
        )

    def handle(self, *args, **options):
        issue_id = options.get("issue_id")
        issue = Issue.objects.get(id=issue_id)

        ipub = logic.issue_to_eschol(issue=issue)
        print(ipub)
        if not ipub.success:
            print(ipub.result)
        for apub in ipub.articlepublicationhistory_set.all():
            print(apub)
            if not apub.success:
                print(apub.result)
            epub = EscholArticle.objects.get(article=apub.article)
            if epub.has_doi_error():
                print(f'\tDOI registered {apub.article.get_doi()}')
            else:
                print(f'\tDOI not registered: {epub.doi_result_text}')