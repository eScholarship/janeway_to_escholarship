from django.core.management.base import BaseCommand

from submission.models import Article
from plugins.eschol import logic

import pprint

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

        epub, error = logic.article_to_eschol(article=article)
        if error:
            print(f'An error occured sending article {article_id} to eScholarship:')
            print(error)
        if epub:
            print(f'Deposited article {article.pk} to eScholarship at {epub.ark}')
            if epub.is_doi_registered:
                print(f'\tDOI registered {article.get_doi()}')
            else:
                print(f'\tDOI not registered: {epub.doi_result_text}')
            