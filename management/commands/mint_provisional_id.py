from django.core.management.base import BaseCommand

from submission.models import Article
from plugins.eschol import logic

class Command(BaseCommand):
    """Mints a provisional id for an article (mostly for testing)"""
    help = "Mints a provisional id for an article"

    def add_arguments(self, parser):
        parser.add_argument(
            "article_id", help="`id` of article that needs an id", type=int
        )

    def handle(self, *args, **options):
        article_id = options.get("article_id")
        article = Article.objects.get(id=article_id)
        ark = logic.get_provisional_id(article)
        print(ark)
        