from django.urls import re_path

from plugins.eschol import views


urlpatterns = [
    re_path(r'^manager/$', views.eschol_manager, name='eschol_manager'),
    re_path(r'^manager/issue/(?P<issue_id>\d+)/$',
            views.list_articles,
            name='eschol_list_articles'),
    re_path(r'^manager/issue/(?P<issue_id>\d+)/publish/$',
            views.publish_issue,
            name='eschol_publish_issue'),
    re_path(r'^manager/article/(?P<article_id>\d+)/publish/$',
            views.publish_article,
            name='eschol_publish_article'),
    re_path(r'^download/(?P<article_id>\d+)/file/(?P<file_id>\d+)/$',
            views.access_article_file,
            name='access_article_file'),
]
