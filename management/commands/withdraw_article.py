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
        parser.add_argument(
            "public_message", help="message to show the public in escholarship", type=str
        )
        parser.add_argument(
            "--internal_comment", help="internal message in escholarship", type=str
        )
        parser.add_argument(
            "--redirect", help="ark to redirect to", type=str
        )

    def handle(self, *args, **options):
        article_id = options.get("article_id")
        article = Article.objects.get(id=article_id)
        #msg = options.get("public_message")
        #args = {}

        #if "internal_comment" in options:
        #    args.update({"internalComment": options.get("internal_comment")})

        #if "redirect" in options:
        #    args.update({"redirectTo": options.get("redirect")})

        #logic.withdraw_item(article, msg, **args)
