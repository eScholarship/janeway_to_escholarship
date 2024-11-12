from datetime import datetime, timedelta

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required

from django_q.tasks import async_task

from submission.models import Article
from journal.models import Issue
from core.models import File
from core import files

from .models import AccessToken, IssuePublicationHistory

from .logic import article_to_eschol, issue_to_eschol
from .plugin_settings import PLUGIN_NAME

def publish_issue_task(issue_id):
    issue = Issue.objects.get(pk=issue_id)
    if not IssuePublicationHistory.objects.filter(issue=issue, is_complete=False).exists():
        ipub = issue_to_eschol(issue=issue)
        return str(ipub)

    return f"{issue} publication in process"

@login_required
def publish_issue(request, issue_id):
    template = 'eschol/issue_publish_queued.html'
    issue = get_object_or_404(Issue, pk=issue_id)
    async_task(publish_issue_task, issue_id, group=issue_id)
    context = {'plugin_name': PLUGIN_NAME,
               'issue': issue}
    return render(request, template, context)

@login_required
def publish_article(request, article_id):
    template = 'eschol/published.html'
    article = get_object_or_404(Article, pk=article_id)
    pub_history  = article_to_eschol(request=request, article=article)
    context = {
        'plugin_name': PLUGIN_NAME,
        'obj': article,
        'pub_history': pub_history,
        'issue': article.issue,
        'obj_name': "Article",
    }
    return render(request, template, context)

@login_required
def list_articles(request, issue_id):
    template = 'eschol/list_articles.html'
    issue = get_object_or_404(Issue, pk=issue_id)
    context = {
        'plugin_name': PLUGIN_NAME,
        'issue': issue,
        'articles': issue.get_sorted_articles(),
        'pub_history': issue.issuepublicationhistory_set.all().order_by('-date')[:10]
    }

    return render(request, template, context)

@login_required
def eschol_manager(request):
    template = 'eschol/manager.html'
    if request.journal:
        issues = Issue.objects.filter(journal=request.journal)
    else:
        issues = Issue.objects.all()

    context = {
        'plugin_name': PLUGIN_NAME,
        'issues': issues
    }

    return render(request, template, context)

def access_article_file(request, article_id, file_id):
    if not "access" in request.GET:
        return HttpResponseForbidden()

    token = request.GET.get("access")
    AccessToken.objects.filter(date__lt=datetime.now()-timedelta(days=1)).delete()
    if not AccessToken.objects.filter(article_id=article_id, file_id=file_id, token=token).exists():
        return HttpResponseForbidden()

    article_object = get_object_or_404(Article, pk=article_id)
    file_object = get_object_or_404(File, pk=file_id)
    return files.serve_file(request, file_object, article_object)
