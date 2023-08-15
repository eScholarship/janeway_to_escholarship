from django.core.management.base import BaseCommand

from journal.models import Issue
from plugins.eschol import logic

import pprint

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

        epubs, errors = logic.issue_to_eschol(issue=issue)
        if len(errors):
            print(f'Errors occured sending issue {issue.pk} to eScholarship:')
            for e in errors:
                print(e)
        if len(epubs):
            print(f'Deposited issue {issue.pk} to eScholarship')
            for epub in epubs:
                print(f'Deposited article {epub.article.pk} to {epub.ark}')
                if epub.is_doi_registered:
                    print(f'\tDOI registered {epub.article.get_doi()}')
                else:
                    print(f'\tDOI not registered: {epub.doi_result_text}')
