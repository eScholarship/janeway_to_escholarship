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
from .plugin_settings import PLUGIN_NAME

from django_q.tasks import async_task
from django_q.tasks import fetch_group

def publish_issue_task(issue_id):
    issue = Issue.objects.get(pk=issue_id)
    epubs, errors = issue_to_eschol(issue=issue)
    if len(errors) > 0:
        return {"success": False, "result": f'Failed to publish {issue}: {";".join(errors)}'}
    else:
        return {"success": True, "result": f"Published {len(epubs)} articles in {issue}"}

def publish_issue_result(task):
    print("publish issue result")
    result = task.result
    task.success = result["success"]
    task.result = result["result"]
    task.hook = None
    task.save()

def publish_issue(request, issue_id):
    template = 'eschol/issue_publish_queued.html'
    issue = get_object_or_404(Issue, pk=issue_id)
    async_task('plugins.eschol.views.publish_issue_task', issue_id, group=issue_id, hook='plugins.eschol.views.publish_issue_result')
    context = {'plugin_name': PLUGIN_NAME,
               'issue': issue}
    return render(request, template, context)

def publish_article(request, article_id):
    template = 'eschol/published.html'
    article = get_object_or_404(Article, pk=article_id)
    epub, error = article_to_eschol(request=request, article=article)
    context = {
        'plugin_name': PLUGIN_NAME,
        'obj': article,
        'objs': [epub] if epub else [],
        'errors': [error] if error else [],
        'issue': article.issue,
        'obj_name': "Article"
    }
    return render(request, template, context)

def list_articles(request, issue_id):
    template = 'eschol/list_articles.html'
    issue = get_object_or_404(Issue, pk=issue_id)
    context = {
        'plugin_name': PLUGIN_NAME,
        'issue': issue,
        'articles': issue.get_sorted_articles(),
        'tasks': fetch_group(issue_id),
    }

    return render(request, template, context)

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
