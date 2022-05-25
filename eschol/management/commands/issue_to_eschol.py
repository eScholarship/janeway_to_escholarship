from django.core.management.base import BaseCommand

from journal.models import Issue
from plugins.eschol import logic

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

        logic.issue_to_eschol(issue=issue)