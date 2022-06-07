from django.shortcuts import render

from plugins.eschol import forms

from submission.models import Article
from journal.models import Issue
from core.models import File
from core import files
from django.http import Http404
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden

from datetime import datetime, timedelta

from .models import AccessToken

from .logic import issue_to_eschol, article_to_eschol

def publish_issue(request, issue_id):
    template = 'eschol/published.html'
    issue = get_object_or_404(Issue, pk=issue_id)
    msg = issue_to_eschol(issue=issue)
    context = {
        'obj': issue,
        'message': msg
    }
    return render(request, template, context)

def publish_article(request, article_id):
    template = 'eschol/published.html'
    article = get_object_or_404(Article, pk=article_id)
    msg = article_to_eschol(article=article)
    context = {
        'obj': article,
        'message': msg
    }
    return render(request, template, context)

def list_articles(request, issue_id):
    template = 'eschol/list_articles.html'
    issue = get_object_or_404(Issue, pk=issue_id)
    context = {
        'issue': issue,
        'articles': issue.get_sorted_articles()
    }

    return render(request, template, context)

def eschol_manager(request):
    template = 'eschol/manager.html'
    # get current journsl?  Look at OAI
    context = {
        'issues': Issue.objects.all()
    }

    return render(request, template, context)


def access_article_file(request, article_id, file_id):
    if not "access" in request.GET:
        return HttpResponseForbidden()

    token = request.GET.get("access")
    AccessToken.objects.filter(date__lt=datetime.now()-timedelta(days=1)).delete()
    if not AccessToken.objects.filter(article_id=article_id, file_id=file_id, token=token).exists():
        return HttpResponseForbidden()

    article_object = Article.objects.get(id=article_id)

    try:
        if file_id != "None":
            file_object = get_object_or_404(File, pk=file_id)
            return files.serve_file(request, file_object, article_object)
        else:
            raise Http404
    except Http404:
        if file_id != "None":
            raise Http404
