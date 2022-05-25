from django.core.management.base import BaseCommand

from submission.models import Article
from plugins.eschol import logic

class Command(BaseCommand):
    """ Deposits specified article in escholarship via graphql api"""
    help = "Deposits specified article in escholarship via graphql api"

    def add_arguments(self, parser):
        parser.add_argument(
            "article_id", help="`id` of article to send to escholarship", type=int
        )

    def handle(self, *args, **options):
        article_id = options.get("article_id")
        article = Article.objects.get(id=article_id)

        logic.article_to_eschol(article=article)