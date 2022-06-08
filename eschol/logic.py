from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from journal.models import ArticleOrdering, SectionOrdering

from plugins.eschol.models import *

from core.models import File

import requests, pprint, json, os
from subprocess import Popen, PIPE
from uuid import uuid4
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes

valid_rights = ["https://creativecommons.org/licenses/by/4.0/",
                "https://creativecommons.org/licenses/by-sa/4.0/",
                "https://creativecommons.org/licenses/by-nd/4.0/",
                "https://creativecommons.org/licenses/by-nc/4.0/",
                "https://creativecommons.org/licenses/by-nc-sa/4.0/",
                "https://creativecommons.org/licenses/by-nc-nd/4.0/"]

deposit_query = """mutation depositItem($item: DepositItemInput!) {
    depositItem(input: $item) {
        id
        message
    }
}
"""

withdraw_query = """mutation withdrawItem($input: WithdrawItemInput!) {
    withdrawItem(input: $input) {
        message
    }
}
"""

mint_query = """mutation mintProvisionalID($input: MintProvisionalIDInput!){
    mintProvisionalID(input: $input){
        id
    }
}
"""

issue_query = """mutation updateIssue($input: UpdateIssueInput!){
    updateIssue(input: $input){
        message
    }
}
"""

def save_article_file(output, article, original_filename, file_mime, owner, label, description):
    filename = str(uuid4()) + str(os.path.splitext(original_filename)[1])
    folder_structure = os.path.join(settings.BASE_DIR, 'files', 'articles', str(article.id))

    if not os.path.exists(folder_structure):
        os.makedirs(folder_structure)

    fpath = os.path.join(folder_structure, filename)
    with open(fpath, 'wb') as f:
        f.write(output)

    new_file = File(mime_type=file_mime,
                    original_filename=original_filename,
                    uuid_filename=filename,
                    label=label,
                    description=description,
                    owner=owner,
                    is_galley=False,
                    article_id=article.pk)

    new_file.save()

    return new_file

def send_to_eschol(query, variables):
    url = settings.ESCHOL_API_URL
    params = {'access': settings.ESCHOL_ACCESS_TOKEN}
    headers = {"Privileged": settings.ESCHOL_PRIV_KEY}
    r = requests.post(url, params=params, json={'query': query, 'variables': variables}, headers=headers)
    return r

def get_provisional_id(article):
    variables = {"input": {"sourceName": "janeway", "sourceID": str(article.pk)}}
    r = send_to_eschol(mint_query, variables)
    data = json.loads(r.text)    
    # TODO: ERROR
    return data["data"]["mintProvisionalID"]["id"]

def get_file_url(article, fid):
    token = AccessToken.objects.create(article_id=article.pk, file_id=fid)
    token.generate_token()
    return "{}{}?access={}".format(article.journal.site_url(),
                                    reverse('access_article_file', kwargs={"article_id": article.pk, "file_id": fid}),
                                    token.token)

def get_supp_file_json(f, article, filename=None):
    return {"file": filename if filename else f.original_filename,
            "contentType": f.mime_type,
            "size": f.get_file_size(article),
            "fetchLink": get_file_url(article, f.pk)}

def get_article_json(article, unit):
    if EscholArticle.objects.filter(article=article).exists():
        epub = EscholArticle.objects.get(article=article)
    else:
        epub = False

    item = {
        "sourceName": "janeway",
        "sourceID": str(article.pk),
        "submitterEmail": article.owner.email,
        "title": article.title,
        "type": "ARTICLE",
        "published": article.date_published.strftime("%Y-%m-%d"),
        "isPeerReviewed": article.peer_reviewed,
        "contentVersion": "PUBLISHER_VERSION",
        "abstract": article.abstract,
        "journal": article.journal.name,
        "sectionHeader": article.section.name,
        "issn": article.journal.issn,
        "units": [unit],
        "language": article.language,
        "pubRelation": "EXTERNAL_PUB",
        "dateSubmitted": article.date_submitted.strftime("%Y-%m-%d"),
        "dateAccepted": article.date_accepted.strftime("%Y-%m-%d"),
        "datePublished": article.date_published.strftime("%Y-%m-%d")
    }

    if article.first_page:
        item["fpage"] = article.first_page

    if article.last_page:
        item["lpage"] = article.last_page

    keywords = list(filter(None, article.keywords.all().values_list('word', flat=True)))
    if len(keywords) > 0:
        item["keywords"] = keywords

    if article.license:
        l = article.license.url
        if not l.endswith("/"):
            l += "/"
        if not l in valid_rights:
            raise Exception("Invalid rights value: {}".format(l))
        item["rights"] = l

    if article.publisher_name:
        item["publisher"] = article.publisher_name

    issue = article.issue
    if issue:
        if SectionOrdering.objects.filter(issue=issue, section=article.section).exists():
            sorder = SectionOrdering.objects.get(issue=issue, section=article.section).order
        else:
            sorder = "1"
        aorder = ArticleOrdering.objects.get(issue=issue, section=article.section, article=article)
        item.update({"volume": str(issue.volume), 
                    "issue": issue.issue,
                    "issueTitle": issue.issue_title,
                    "issueDate": issue.date.strftime("%Y-%m-%d"),
                    "issueDescription": issue.issue_description,
                    'orderInSection': int(sorder + str(aorder.order).zfill(4))})

    authors = []
    for a in article.authors.all():
        parts = {"fname": a.first_name,
                "lname": a.last_name,
                "institution": a.institution}
        if a.middle_name:
            parts.update({"mname": a.middle_name})
        author = {
            "email": a.email,
            "nameParts": parts
        }
        if a.orcid:
            author.update({"orcid": a.orcid})
        authors.append(author)
    
    if len(authors) > 0:
        item["authors"]  = authors

    funders = []
    for f in article.funders.all():
        funders.append({
            "name": f.name,
            "reference": f.funding_id
        })
    if len(funders) > 0:
        item["grants"] = funders

    rg = article.get_render_galley
    if not rg:
        rg = article.galley_set.filter(file__mime_type="application/pdf")\
                    .order_by("sequence",)[0]

    suppFiles = []
    img_files = []
    if rg.is_remote:
        item.update({"externalLinks": [rg.remote_file]})
    elif rg.file:
        if rg.file.mime_type == 'application/xml' or rg.file.mime_type == 'text/xml':
            r = render_to_string("eschol/escholarship.html", {'article_content': rg.render(recover=True), 'css_file': rg.css_file})
            s = force_bytes(r,  encoding="utf-8")
            p = Popen(['xmllint', '--html', '--xmlout', '--format', '--encode', 'utf-8', '/dev/stdin'], stdin=PIPE, stdout=PIPE)
            (output, error_output) = p.communicate(s)
            if not epub:
                ark = get_provisional_id(article)
                epub = EscholArticle.objects.create(article=article, ark=ark)
            else:
                ark = epub.ark
            short_ark = ark.split("/")[-1]
            html_filename = "{}.html".format(short_ark)
            html_files = File.objects.filter(original_filename=html_filename, article_id=article.id)
            if html_files.exists():
                html_files.delete()
            html_file = save_article_file(output, article, html_filename, "text/html", 
                                          article.owner, label="Generated HTML", 
                                          description="HTML file generated from JATS for eschol")
            item.update({
                "id": ark,
                "contentLink": get_file_url(article, html_file.pk),
                "contentFileName": html_file.original_filename,
            })
            # add xml and pdf to suppFiles
            suppFiles.append(get_supp_file_json(rg.file, article, filename="{}.xml".format(short_ark)))
            pdfs = article.pdfs
            if len(pdfs) > 0:
                suppFiles.append(get_supp_file_json(pdfs[0].file, article, filename="{}.pdf".format(short_ark)))
            for imgf in rg.images.all():
                img_files.append({"file": imgf.original_filename, "fetchLink": imgf.remote_url if imgf.is_remote else get_file_url(article, imgf.pk)})
            if rg.css_file:
                css = rg.css_file
                item.update({"cssFiles": {"file": css.original_filename,
                                          "fetchLink": css.remote_url if css.is_remote else get_file_url(article, css.pk)}})
        else:
            item.update({
                "contentLink": get_file_url(article, rg.file.pk),
                "contentFileName": rg.file.original_filename,
            })
        
    for f in article.supplementary_files.all():
        suppFiles.append(get_supp_file_json(f.file, article))

    if len(suppFiles):
        item.update({"suppFiles": suppFiles})

    if len(img_files):
        item.update({"imgFiles": img_files})

    local_ids = []
    for i in article.identifiers.all():
        if i.id_type == "doi":
            x = {"id": i.identifier,
                "scheme": "DOI"}
        else:
            x = {"id": i.identifier,
                "scheme": "OTHER_ID",
                "subScheme": i.id_type}
        local_ids.append(x)

    if len(local_ids) > 0:
        item.update({"localIDs": local_ids})

    return item, epub

def withdraw_item(article, public_message, **args):
    input = {"id": "",  "public_message": public_message}
    input.update(args)

    variables = {"input": input}
    r = send_to_eschol(withdraw_query, variables)

    pprint.pprint(r.text)

def get_unit(journal):
    if JournalUnit.objects.filter(journal=journal).exists():
        unit = JournalUnit.objects.get(journal=journal).unit
    else:
        unit = journal.code
    return unit

def send_article(article):
    unit = get_unit(article.journal)
    try:
        (item, epub) = get_article_json(article, unit)
        if epub:
            item["id"] = epub.ark

        #print(epub)

        pprint.pprint(item)

        variables = {"item": item}
        r = send_to_eschol(deposit_query, variables)

        data = json.loads(r.text)
        print(data)
        if "data" in data:
            di = data["data"]["depositItem"]
            msg = "{}: {}".format(di["message"], di["id"])
            if epub:
                epub.save()
            else:
                EscholArticle.objects.create(article=article, ark=di["id"])
        else:
            msg = data["errors"]
    except json.decoder.JSONDecodeError:
        msg = r.text
    except Exception as e:
        msg = str(e)

    return msg

def issue_to_eschol(**options):
    issue = options.get("issue")
    unit = get_unit(issue.journal)

    cover_url = "{}{}".format(issue.journal.site_url(), issue.cover_image.url)
    variables = {"input": {"journal": unit,
                           "issue": int(issue.issue),
                           "volume": issue.volume,
                           "coverImageURL": cover_url}}

    pprint.pprint(variables)
    r = send_to_eschol(issue_query, variables)
    print(r.text)

    for a in issue.get_sorted_articles():
        msg = send_article(a)
        print(msg)

def article_to_eschol(**options):
    article = options.get("article")
    msg = send_article(article)
    print(msg)