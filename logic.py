import json, os, time
from subprocess import Popen, PIPE
from uuid import uuid4

import requests

from django.conf import settings
from django.urls import reverse
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes

from journal.models import ArticleOrdering, SectionOrdering
from core.models import File, XSLFile
from core.files import PDF_MIMETYPES

from plugins.eschol.models import (JournalUnit,
                                   EscholArticle,
                                   AccessToken,
                                   ArticlePublicationHistory,
                                   IssuePublicationHistory)

from utils import logic as utils_logic
from utils.logger import get_logger
logger = get_logger(__name__)

VALID_RIGHTS = ["https://creativecommons.org/licenses/by/4.0/",
                "https://creativecommons.org/licenses/by-sa/4.0/",
                "https://creativecommons.org/licenses/by-nd/4.0/",
                "https://creativecommons.org/licenses/by-nc/4.0/",
                "https://creativecommons.org/licenses/by-nc-sa/4.0/",
                "https://creativecommons.org/licenses/by-nc-nd/4.0/"]

DEPOSIT_QUERY = """mutation depositItem($item: DepositItemInput!) {
    depositItem(input: $item) {
        id
        message
    }
}
"""

MINT_QUERY = """mutation mintProvisionalID($input: MintProvisionalIDInput!){
    mintProvisionalID(input: $input){
        id
    }
}
"""

ISSUE_QUERY = """mutation updateIssue($input: UpdateIssueInput!){
    updateIssue(input: $input){
        message
    }
}
"""

def save_article_file(output, article, original_filename, kwargs=None):
    filename = str(uuid4()) + str(os.path.splitext(original_filename)[1])
    folder_structure = os.path.join(settings.BASE_DIR, 'files', 'articles', str(article.id))

    if not os.path.exists(folder_structure):
        os.makedirs(folder_structure)

    fpath = os.path.join(folder_structure, filename)
    with open(fpath, 'wb') as f:
        f.write(output)

    new_file = File.objects.create(original_filename=original_filename,
                                   uuid_filename=filename,
                                   is_galley=False,
                                   article_id=article.pk,
                                    **kwargs)

    new_file.save()

    return new_file

def send_to_eschol(query, variables):
    url = settings.ESCHOL_API_URL
    params = {'access': settings.ESCHOL_ACCESS_TOKEN}
    headers = {"Privileged": settings.ESCHOL_PRIV_KEY}
    r = requests.post(url,
                      params=params,
                      json={'query': query, 'variables': variables},
                      headers=headers,
                      timeout=(5, 10))
    if "Mysql2::Error: Deadlock" in r.text:
        time.sleep(5)
        send_to_eschol(query, variables)
    return r

def get_provisional_id(article):
    if hasattr(settings, 'ESCHOL_API_URL'):
        variables = {"input": {"sourceName": "janeway", "sourceID": str(article.pk)}}
        r = send_to_eschol(MINT_QUERY, variables)
        data = json.loads(r.text)
        return data["data"]["mintProvisionalID"]["id"]

    # Return a fake ark if we're not connected to the API
    return "ark:/13030/qtXXXXXXXX"

def get_file_url(article, fid):
    token = AccessToken.objects.create(article_id=article.pk, file_id=fid)
    token.generate_token()
    url = article.journal.site_url(path=reverse('access_article_file',
                                   kwargs={"article_id": article.pk,
                                           "file_id": fid}))
    return f"{url}?access={token.token}"

def get_supp_file_json(f, article, filename=None, title=None):
    x = {"file": filename if filename else f.original_filename,
         "contentType": f.mime_type,
         "size": f.get_file_size(article),
        "fetchLink": get_file_url(article, f.pk)}
    if title:
        x.update({"title": title})
    return x

def convert_data_availability(d):
    types = {"Public repository": "publicRepo",
            "Public repository: available after publication": "publicRepoLater",
            "Supplemental files": "suppFiles",
            "Within the manuscript": "withinManuscript",
            "Available upon request": "onRequest",
            "Managed by a third party": "thirdParty",
            "Not available": "notAvail"}

    for f in d:
        if f.answer in types:
            return types.get(f.answer, None)
    return None

def xml_galley_to_html(article, galley, epub):
    item = {}
    supp_files = []
    img_files = []
    # if the galley doesn't have an xsl file it will cause an error when rendering
    # so set it to the default
    if not galley.xsl_file:
        galley.xsl_file = XSLFile.objects.get(label=settings.DEFAULT_XSL_FILE_LABEL)
        galley.save()

    context = {'article_content': galley.render(recover=True),
               'default_css_url': get_default_css_url(article.journal),
               'css_file': galley.css_file}
    r = render_to_string("eschol/escholarship.html", context)
    s = force_bytes(r,  encoding="utf-8")
    with Popen(['xmllint', '--html', '--xmlout', '--format', '--encode', 'utf-8', '/dev/stdin'],
              stdin=PIPE,
              stdout=PIPE) as p:
        (output, _error_output) = p.communicate(s)
    if not epub:
        ark = get_provisional_id(article)
        epub = EscholArticle.objects.create(article=article, ark=ark)
    else:
        ark = epub.ark

    short_ark = ark.split("/")[-1]
    html_filename = f"{short_ark}.html"
    html_files = File.objects.filter(original_filename=html_filename, article_id=article.id)
    if html_files.exists():
        html_files.delete()
    kwargs = {'mime_type': "text/html",
              'owner': article.owner,
              'label': "Generated HTML",
              'description': "HTML file generated from JATS for eschol"}
    html_file = save_article_file(output, article, html_filename, kwargs=kwargs)
    item.update({"id": ark,
                 "contentLink": get_file_url(article, html_file.pk),
                 "contentFileName": html_file.original_filename,})

    # add xml and pdf to suppFiles
    supp_files.append(get_supp_file_json(galley.file,
                                         article,
                                         filename=f"{short_ark}.xml",
                                         title=f"[XML] {article.title}"))

    # look for the PDF galley there should only be one but
    # we'll take the first one regardless
    # first look in the galleys marked as type "PDF"
    # if we don't find any look for galley with files with
    # mime_type = pdf
    pdfs = article.pdfs.filter(public=True)
    if len(pdfs) == 0:
        pdfs = article.galley_set.filter(type="", file__mime_type__in=PDF_MIMETYPES, public=True)

    if len(pdfs) > 0:
        supp_files.append(get_supp_file_json(pdfs[0].file,
                                             article,
                                             filename=f"{short_ark}.pdf",
                                             title=f"[PDF] {article.title}"))

    for imgf in galley.images.all():
        flink = imgf.remote_url if imgf.is_remote else get_file_url(article, imgf.pk)
        img_files.append({"file": imgf.original_filename, "fetchLink": flink})

    if galley.css_file:
        css = galley.css_file
        flink = css.remote_url if css.is_remote else get_file_url(article, css.pk)
        item.update({"cssFiles": {"file": css.original_filename, "fetchLink": flink}})

    return item, supp_files, img_files, epub

def get_article_json(article, unit):
    source_name = "janeway"
    source_id = article.pk
    if EscholArticle.objects.filter(article=article).exists():
        epub = EscholArticle.objects.get(article=article)
        if epub.source_name:
            source_name = epub.source_name
            source_id = epub.source_id
            if not source_id:
                msg = f"{article} has source {epub.source_name} but source_id is not defined"
                logger.error(msg)
    else:
        epub = False

    item = {
        "sourceName": source_name, # required
        "sourceID": str(source_id), # required
        "sourceURL": article.journal.press.domain,
        "submitterEmail": article.owner.email, # required
        "title": article.title, # required
        "type": "ARTICLE", # required
        "published": article.date_published.strftime("%Y-%m-%d"), # required
        "isPeerReviewed": article.peer_reviewed, # required
        "contentVersion": "PUBLISHER_VERSION",
        "journal": article.journal.name,
        "units": [unit], # required
        "pubRelation": "EXTERNAL_PUB"
    }

    if article.abstract:
        item["abstract"] = article.abstract

    if article.journal.issn and not article.journal.issn == '0000-0000':
        item["issn"] = article.journal.issn

    if article.date_submitted:
        item["dateSubmitted"] = article.date_submitted.strftime("%Y-%m-%d")

    if article.date_accepted:
        item["dateAccepted"] = article.date_accepted.strftime("%Y-%m-%d")

    if article.date_published:
        item["datePublished"] = article.date_published.strftime("%Y-%m-%d")

    if article.custom_how_to_cite:
        item["customCitation"] = article.custom_how_to_cite

    if article.first_page:
        item["fpage"] = str(article.first_page)

    if article.last_page:
        item["lpage"] = str(article.last_page)

    if article.language:
        item["language"] = article.language

    if article.section:
        if article.section.plural and article.section.article_count() > 1:
            h = article.section.plural
        else:
            h = article.section.name
        item["sectionHeader"] =  h

    keywords = list(filter(None, article.keywords.all().values_list('word', flat=True)))
    if len(keywords) > 0:
        item["keywords"] = keywords

    if article.license:
        l = article.license.url
        if not l.endswith("/"):
            l += "/"
        if l in VALID_RIGHTS:
            item["rights"] = l

    if article.publisher_name:
        item["publisher"] = article.publisher_name

    data_avail_set = article.fieldanswer_set.filter(field__name="Data Availability")
    if data_avail_set.exists():
        data_avail = convert_data_availability(data_avail_set)
        if data_avail:
            item["dataAvailability"] = data_avail
            if item["dataAvailability"] == "publicRepo":
                data_url_set = article.fieldanswer_set.filter(field__name="Data URL")
                if data_url_set.exists():
                    item["dataURL"] = data_url_set[0].answer

    issue = article.issue
    if issue:
        if SectionOrdering.objects.filter(issue=issue, section=article.section).exists():
            sorder = SectionOrdering.objects.get(issue=issue, section=article.section).order + 1
        else:
            sorder = 1
        if ArticleOrdering.objects.filter(issue=issue,
                                          section=article.section,
                                          article=article).exists():
            aorder = ArticleOrdering.objects.get(issue=issue,
                                                 section=article.section,
                                                 article=article).order + 1
        else:
            aorder = 1
        issue_vars = {"volume": str(issue.volume),
                      "issue": str(issue.issue),
                      "issueTitle": issue.issue_title,
                      "issueDate": issue.date.strftime("%Y-%m-%d"),
                      "orderInSection": int(str(sorder) + str(aorder).zfill(4))}
        if issue.issue_description:
            issue_vars["issueDescription"] = issue.issue_description
        if issue.short_description:
            issue_vars["issueCoverCaption"] = issue.short_description
        item.update(issue_vars)

    authors = []
    for fa in article.frozen_authors().all():
        if fa.is_corporate:
            parts = {"organization": fa.institution}
        else:
            parts = {"fname": fa.first_name,
                     "lname": fa.last_name}
            if fa.institution:
                parts.update({"institution": fa.institution})
            if fa.middle_name:
                parts.update({"mname": fa.middle_name})
        author = {
            "nameParts": parts
        }
        if fa.email:
            author.update({"email": fa.email})
        if fa.orcid:
            author.update({"orcid": fa.orcid})
        authors.append(author)

    if len(authors) > 0:
        item["authors"]  = authors

    # funders = []
    # for f in article.funders.all():
    #     funders.append({
    #         "name": f.name,
    #         "reference": f.fundref_id
    #     })
    # if len(funders) > 0:
    #     item["grants"] = funders

    rg = article.get_render_galley

    if not rg and article.galley_set.filter(file__mime_type="application/pdf",
                                            public=True).exists():
        rg = article.galley_set.filter(file__mime_type="application/pdf", public=True)\
                               .order_by("sequence",)[0]

    supp_files = []
    img_files = []
    # If there's no galley just leave it out
    if rg and rg.public:
        if rg.is_remote:
            item.update({"externalLinks": [rg.remote_file]})
        elif rg.file:
            if rg.file.mime_type in ('application/xml', 'text/xml'):
                fields, supp_files, img_files, epub = xml_galley_to_html(article, rg, epub)
                item.update(fields)
            else:
                item.update({
                    "contentLink": get_file_url(article, rg.file.pk),
                    "contentFileName": rg.file.original_filename,
                })

    for f in article.supplementary_files.all():
        supp_files.append(get_supp_file_json(f.file, article))

    if len(supp_files) > 0:
        item.update({"suppFiles": supp_files})

    if len(img_files) > 0:
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

    local_ids.append({"id": f'janeway_{article.pk}',
                      "scheme": "OTHER_ID",
                      "subScheme": "other"})

    if len(local_ids) > 0:
        item.update({"localIDs": local_ids})

    return item, epub

def get_default_css_url(journal):
    if JournalUnit.objects.filter(journal=journal).exists():
        return JournalUnit.objects.get(journal=journal).default_css_url
    return None

def get_unit(journal):
    if JournalUnit.objects.filter(journal=journal).exists():
        unit = JournalUnit.objects.get(journal=journal).unit
    else:
        unit = journal.code
    return unit

def register_doi(article, epub, request):
    try:
        # it would be better to refactor so it doesn't depend directly on ezid plugin
        from plugins.ezid.logic import register_journal_doi, update_journal_doi # pylint: disable=import-outside-toplevel
        if not epub.is_doi_registered:
            enabled, success, result_text = register_journal_doi(article, request)
        else:
            enabled, success, result_text = update_journal_doi(article, request)
        if enabled:
            epub.is_doi_registered = success or epub.is_doi_registered
            epub.doi_result_text = result_text
            epub.save()
    except (ImportError, ModuleNotFoundError):
        # If we don't find the ezid plugin just don't register.  it's fine.
        pass
    except Exception as e: #pylint: disable=broad-exception-caught
        # log unexpected error and report a shorter message to the user
        msg = f'An unexpected error occured when registering DOI for {article}: {e}'
        logger.error(e, exc_info=True)
        if request: messages.error(request, msg)

def article_error(article, request, msg):
    logger.info(msg)
    if request: messages.error(request, msg)
    return ArticlePublicationHistory.objects.create(article=article,
                                                    success=False,
                                                    result=msg)

def send_article(article, configured=False, request=None):
    unit = get_unit(article.journal)

    if not article.is_published:
        return article_error(article, request, f'{article} is not published')

    if not article.issue:
        return article_error(article, request, f'{article} published without issue')

    if not article.owner:
        return article_error(article, request, f'{article} published without owner')

    if not article.title:
        return article_error(article, request, f'{article} published without title')

    rg = article.get_render_galley
    if rg and not rg.public:
        return article_error(article, request, f'Private render galley selected for {article}')

    item, epub = get_article_json(article, unit)
    if epub:
        item["id"] = epub.ark

    variables = {"item": item}
    if configured:
        r = send_to_eschol(DEPOSIT_QUERY, variables)

        try:
            data = json.loads(r.text)
            if "data" in data:
                di = data["data"]["depositItem"]
                msg = f'{di["message"]}: {di["id"]}'
                logger.info(msg)
                if request: messages.success(request, msg)
                if epub:
                    epub.save()
                else:
                    epub = EscholArticle.objects.create(article=article, ark=di["id"])
                article.is_remote = True
                article.remote_url = epub.get_eschol_url()
                article.save()
                if article.get_doi():
                    register_doi(article, epub, request)
                else:
                    msg = f"{article} published without DOI"
                    logger.warning(msg)
                    if request: messages.warning(request, msg)
            else:
                error_msg = f'ERROR sending Article {article.pk} to eScholarship: {data["errors"]}'
                return article_error(article, request, error_msg)
        except json.decoder.JSONDecodeError:
            msg = f"An unexpected API error occured sending {article} to eScholarship"
            apub = article_error(article, request, msg)
            logger.error(r.text)
            return apub
    else:
        logger.debug(f'Escholarhip Deposit for Article {article.pk}: {variables}')
        msg = f"eScholarship API not configured: {article} not sent"
        return article_error(article, request, msg)

    return ArticlePublicationHistory.objects.create(article=article, success=True,)

def send_issue_meta(issue, configured=False):
    success = False
    msg = None
    if issue.cover_image and issue.cover_image.url:
        unit = get_unit(issue.journal)

        # media are hosted at ://domain/media not ://domain/site_code/media
        # this is the most consistent way I can find to generate this url
        j = issue.journal
        cover_url = utils_logic.build_url(netloc=j.press.domain,
                                          scheme=j.press.SCHEMES[j.press.is_secure],
                                          port=None,
                                          path=issue.cover_image.url)
        try:
            variables = {"input": {"journal": unit,
                                   "issue": int(issue.issue),
                                   "volume": issue.volume,
                                   "coverImageURL": cover_url}}
        except ValueError:
            success = False
            msg = f"Cannot upload cover images for non-integer issue number {issue.issue}"
            return success, msg


        if configured:
            r = send_to_eschol(ISSUE_QUERY, variables)
            d = json.loads(r.text)
            if "errors" in d:
                success = False
                msg = ";".join([x["message"] for x in d["errors"]])
            elif "data" in d and d["data"]["updateIssue"]["message"] == "Cover Image uploaded":
                success = True
                msg = d["data"]["updateIssue"]["message"]
            else:
                success = False
                msg = r.text
        else:
            success = True
            msg = f'Escholarship deposit {issue}: {variables}'
            logger.debug(msg)
    else:
        success = True
        msg = "No cover image"

    return success, msg

def is_configured():
    if hasattr(settings, 'ESCHOL_API_URL'):
        return True

    logger.info("Escholarship API not configured.")
    return False

def issue_to_eschol(**options):
    request = options.get("request")
    issue = options.get("issue")
    configured = is_configured()

    try:
        success, msg = send_issue_meta(issue, configured)

        ipub = IssuePublicationHistory.objects.create(issue=issue, success=success, result=msg)

        for a in issue.get_sorted_articles():
            apub = send_article(a, configured, request)
            ipub.success = ipub.success and apub.success
            apub.issue_pub = ipub
            apub.save()
    except Exception as e: #pylint: disable=broad-exception-caught
        msg = f'An unexpected error occured when sending {issue} to eScholarship: {e}'
        logger.error(e, exc_info=True)
        if request: messages.error(request, msg)
        ipub = IssuePublicationHistory.objects.create(issue=issue, success=False, result=msg)

    ipub.is_complete = True
    ipub.save()

    return ipub

def article_to_eschol(**options):
    request = options.get('request')
    article = options.get("article")
    configured = is_configured()

    try:
        return send_article(article, configured, request)
    except Exception as e: #pylint: disable=broad-exception-caught
        msg = f'An unexpected error occured when sending {article} to eScholarship: {e}'
        return article_error(article, request, msg)
