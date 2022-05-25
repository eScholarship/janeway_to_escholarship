from django.core.management.base import BaseCommand
from django.conf import settings

import requests, pprint, json

class Command(BaseCommand):
    """Retrieves and prints a given article from escholarship via graphql api"""
    help = "Retrieves and prints a given article from escholarship via graphql api"

    def add_arguments(self, parser):
        parser.add_argument(
            "ark", help="`ark` of article to retrieve from escholarship", type=str
        )

    def handle(self, *args, **options):
        ark = options.get("ark")
        query = """query itemByID($id: ID!) {
            item(id: $id) {
                id
                abstract
                added
                contentLink
                contentSize
                contentType
                externalLinks
                fpage
                grants
                isPeerReviewed
                issue
                journal
                keywords
                language
                localIDs {
                    id
                    scheme
                    subScheme
                }
                lpage
                nativeFileName
                nativeFileSize
                published
                source
                status
                subjects
                suppFiles {
                    contentType
                    downloadLink
                    file
                    size
                }
                title
                type
                units {
                    id
                    type
                }
                updated
                volume
            } 
        }"""

        variables = {"id": ark}

        url = settings.ESCHOL_API_URL
        #params = {'access': settings.ESCHOL_ACCESS_TOKEN}
        #headers = {"Privileged": settings.ESCHOL_PRIV_KEY}
        r = requests.post(url, json={'query': query, 'variables': variables})

        json_data = json.loads(r.text)

        pprint.pprint(json_data)

