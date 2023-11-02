# janeway_to_escholarship
Janeway plugin to deposit to escholarship

## Management commands

* `add_arks <journal-code> <import-file>` - adds arks and dois to articles in a given journal from a jschol export file
* `article_from_eschol <ark>` - Retrieves and prints a given article from escholarship via graphql api (used for testing otherwise not useful)
* `article_to_eschol <article-id>` - If eschol API is configured send the given article to escholarship via the configured API endpoint.  Else print the API call to output.
* `issue_to_eschol <issue_id>` - sends an entire issue including cover image  and all articles to eScholarship.
* `mint_provisional_id` - Used for testing
* `withdraw_article` - Not used or tested

## Models

* EscholArticle -- Should exist for every article that exists in eScholarship contains, ark, date_published from janeway, is_doi_registered, doi_result_text, source_name (for articles that originated in ojs this should be ojs if it's blank it will default to janeway)

* Journal Units
> * Journal
> * Unit -- should be the unit code in escholarship. If no journal unit exists for a journal the `code` field in the journal will be used by default
> * Default css url (optional) -- CSS link that will be added to every HTML file generated from XML. It's only relevent for HTML journals.  All css files that are included directly with articles will also be included and sent to eScholarship but this allows admin to have the same externally hosted file included for all articles. (used by Glossa)

## Tests

There is a *very* small group of tests written as standard django test cases. The following command will run the tests.  You must install the plugin in a directory called "eschol"

```
manage.py test eschol
```

## Dev env setup

If you want to test this plugin from a local janeway dev environment to a local escholAPI instance you should set:

```
ESCHOL_API_URL = 'http://host.docker.internal:4001/graphql'
```
