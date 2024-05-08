from django.conf import settings
from django.urls import reverse
from django.contrib import messages

from journal.models import ArticleOrdering, SectionOrdering
from core.models import File, XSLFile

from plugins.eschol.models import *

import requests, pprint, json, os
from subprocess import Popen, PIPE
from uuid import uuid4
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from core.files import PDF_MIMETYPES

from utils import logic as utils_logic

from utils.logger import get_logger
logger = get_logger(__name__)

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
    if hasattr(settings, 'ESCHOL_API_URL'):
        variables = {"input": {"sourceName": "janeway", "sourceID": str(article.pk)}}
        r = send_to_eschol(mint_query, variables)
        data = json.loads(r.text)
        return data["data"]["mintProvisionalID"]["id"]
    else:
        # Return a fake ark if we're not connected to the API
        return "ark:/13030/qtXXXXXXXX"

def get_file_url(article, fid):
    token = AccessToken.objects.create(article_id=article.pk, file_id=fid)
    token.generate_token()
    return "{}?access={}".format(article.journal.site_url(path=reverse('access_article_file', kwargs={"article_id": article.pk, "file_id": fid})),
                                   token.token)

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
    suppFiles = []
    img_files = []
    # if the galley doesn't have an xsl file it will cause an error when rendering
    # so set it to the default
    if not galley.xsl_file:
        galley.xsl_file = XSLFile.objects.get(label=settings.DEFAULT_XSL_FILE_LABEL)
        galley.save()

    r = render_to_string("eschol/escholarship.html", {'article_content': galley.render(recover=True),
                                                      'default_css_url': get_default_css_url(article.journal),
                                                      'css_file': galley.css_file})
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
    item.update({"id": ark,
                 "contentLink": get_file_url(article, html_file.pk),
                 "contentFileName": html_file.original_filename,})

    # add xml and pdf to suppFiles
    suppFiles.append(get_supp_file_json(galley.file,
                                        article,
                                        filename="{}.xml".format(short_ark),
                                        title="[XML] {}".format(article.title)))

    # look for the PDF galley there should only be one but
    # we'll take the first one regardless
    # first look in the galleys marked as type "PDF"
    # if we don't find any look for galley with files with
    # mime_type = pdf
    pdfs = article.pdfs.filter(public=True)
    if len(pdfs) == 0:
        pdfs = article.galley_set.filter(type="", file__mime_type__in=PDF_MIMETYPES, public=True)

    if len(pdfs) > 0:
        suppFiles.append(get_supp_file_json(pdfs[0].file,
                                            article,
                                            filename="{}.pdf".format(short_ark),
                                            title="[PDF] {}".format(article.title)))

    for imgf in galley.images.all():
        img_files.append({"file": imgf.original_filename, "fetchLink": imgf.remote_url if imgf.is_remote else get_file_url(article, imgf.pk)})

    if galley.css_file:
        css = galley.css_file
        item.update({"cssFiles": {"file": css.original_filename,
                                  "fetchLink": css.remote_url if css.is_remote else get_file_url(article, css.pk)}})

    return item, suppFiles, img_files, epub

def get_article_json(article, unit):
    sourceName = "janeway"
    sourceID = article.pk
    if EscholArticle.objects.filter(article=article).exists():
        epub = EscholArticle.objects.get(article=article)
        if epub.source_name:
            sourceName = epub.source_name
            sourceID = epub.source_id
            if not sourceID:
                logger.error(f"{article} has source {epub.source_name} but source_id is not defined")
    else:
        epub = False

    item = {
        "sourceName": sourceName, # required
        "sourceID": str(sourceID), # required
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
        if l in valid_rights:
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
        if ArticleOrdering.objects.filter(issue=issue, section=article.section, article=article).exists():
            aorder = ArticleOrdering.objects.get(issue=issue, section=article.section, article=article).order + 1
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

    funders = []
    for f in article.funders.all():
        funders.append({
            "name": f.name,
            "reference": f.fundref_id
        })
    if len(funders) > 0:
        item["grants"] = funders

    rg = article.get_render_galley
    if not rg and article.galley_set.filter(file__mime_type="application/pdf", public=True).exists():
        rg = article.galley_set.filter(file__mime_type="application/pdf", public=True)\
                               .order_by("sequence",)[0]

    supp_files = []
    img_files = []
    # If there's no galley just leave it out
    if rg and rg.public:
        if rg.is_remote:
            item.update({"externalLinks": [rg.remote_file]})
        elif rg.file:
            if rg.file.mime_type == 'application/xml' or rg.file.mime_type == 'text/xml':
                fields, supp_files, img_files, epub = xml_galley_to_html(article, rg, epub)
                item.update(fields)
            else:
                item.update({
                    "contentLink": get_file_url(article, rg.file.pk),
                    "contentFileName": rg.file.original_filename,
                })
        
    for f in article.supplementary_files.all():
        supp_files.append(get_supp_file_json(f.file, article))

    if len(supp_files):
        item.update({"suppFiles": supp_files})

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

    local_ids.append({"id": f'janeway_{article.pk}',
                      "scheme": "OTHER_ID",
                      "subScheme": "other"})

    if len(local_ids) > 0:
        item.update({"localIDs": local_ids})

    return item, epub

def withdraw_item(article, public_message, **args):
    input = {"id": "",  "public_message": public_message}
    input.update(args)

    variables = {"input": input}
    r = send_to_eschol(withdraw_query, variables)

    pprint.pprint(r.text)

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
        from plugins.ezid.logic import register_journal_doi, update_journal_doi
        if not epub.is_doi_registered:
            enabled, success, result_text = register_journal_doi(article, request)
        else:
            enabled, success, result_text = update_journal_doi(article, request)
        if enabled:
            epub.is_doi_registered = success
            epub.doi_result_text = result_text
            epub.save()
    except ImportError or ModuleNotFoundError:
        # If we don't find the ezid plugin just don't register.  it's fine.
        pass
    except Exception as e:
        # if we get another type of error log it
        msg = f'An unexpected error occured when registering DOI for {article}: {e}'
        logger.error(e, exc_info=True)
        if request: messages.error(request, msg)

def send_article(article, is_configured=False, request=None):
    unit = get_unit(article.journal)

    if not article.is_published:
        msg = f'{article} is not published'
        logger.info(msg)
        if request: messages.error(request, msg)
        return None, msg

    if not article.issue:
        msg = f'{article} published without issue'
        logger.info(msg)
        if request: messages.error(request, msg)
        return None, msg

    if not article.owner:
        msg = f'{article} published without owner'
        logger.info(msg)
        if request: messages.error(request, msg)
        return None, msg

    if not article.title:
        msg = f'{article} published without title'
        logger.info(msg)
        if request: messages.error(request, msg)
        return None, msg

    item, epub = get_article_json(article, unit)
    if epub:
        item["id"] = epub.ark

    variables = {"item": item}
    if is_configured:
        r = send_to_eschol(deposit_query, variables)

        try:
            data = json.loads(r.text)
            if "data" in data:
                di = data["data"]["depositItem"]
                msg = "{}: {}".format(di["message"], di["id"])
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
                logger.error(error_msg)
                if request: messages.error(request, error_msg)
                return None, error_msg
        except json.decoder.JSONDecodeError:
            logger.error(r.text)
            return None, f"An unexpected API error occured sending {article} to eScholarship"
    else:
        logger.debug(f'Escholarhip Deposit for Article {article.pk}: {variables}')
        msg = f"eScholarship API not configured: {article} not sent"
        if request: messages.error(request, msg)
        return None, msg

    return epub, None

def send_issue_meta(issue, is_configured=False):
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
            return False, f"Cannot upload cover images for non-integer issue number {issue.issue}"

        if is_configured:
            r = send_to_eschol(issue_query, variables)
            d = json.loads(r.text)
            if "errors" in d:
                return False, ";".join([x["message"] for x in d["errors"]])
            elif "data" in d and d["data"]["updateIssue"]["message"] == "Cover Image uploaded":
                return True, "Cover Image uploaded"
            else:
                return False, r.text
        else:
            msg = f'Escholarship deposit {issue}: {variables}'
            logger.debug(msg)
            return True, msg
    return True, "No cover image"

def is_configured():
    if hasattr(settings, 'ESCHOL_API_URL'):
        return True
    else:
        logger.info("Escholarship API not configured.")
        return False

def issue_to_eschol(**options):
    request = options.get("request")
    issue = options.get("issue")
    configured = is_configured()
    objs = []
    errors = []

    try:
        success, msg = send_issue_meta(issue, configured)
        if not success:
            errors.append(msg)

        for a in issue.get_sorted_articles():
            obj, error = send_article(a, configured, request)
            if obj:
                objs.append(obj)
            else:
                errors.append(error)
    except Exception as e:
        msg = f'An unexpected error occured when sending {issue} to eScholarship: {e}'
        logger.error(e, exc_info=True)
        if request: messages.error(request, msg)
        errors.append(msg)

    return objs, errors

def article_to_eschol(**options):
    request = options.get('request')
    article = options.get("article")
    configured = is_configured()

    try:
        return send_article(article, configured, request)
    except Exception as e:
        msg = f'An unexpected error occured when sending {article} to eScholarship: {e}'
        logger.error(e, exc_info=True)
        if request: messages.error(request, msg)

    return None, msg
