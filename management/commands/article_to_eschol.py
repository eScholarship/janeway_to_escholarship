from django.core.management.base import BaseCommand

from submission.models import Article
from plugins.eschol import logic
from plugins.eschol.models import EscholArticle

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

        apub = logic.article_to_eschol(article=article)
        if apub.success:
            print(f'Deposited article {article.pk} to eScholarship at {epub.ark}')
            epub = EscholArticle.objects.get(article=article)
            if epub.has_doi_error():
                print(f'\tDOI registered {article.get_doi()}')
            else:
                print(f'\tDOI not registered: {epub.doi_result_text}')
        else:
            print(f'An error occured sending article {article_id} to eScholarship:')
            print(apub.result)