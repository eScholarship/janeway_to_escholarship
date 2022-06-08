from django.conf.urls import url

from plugins.eschol import views


urlpatterns = [
    url(r'^manager/$', views.eschol_manager, name='eschol_manager'),
    url(r'^manager/issue/(?P<issue_id>\d+)/$', views.list_articles, name='eschol_list_articles'),
    url(r'^manager/issue/(?P<issue_id>\d+)/publish/$', views.publish_issue, name='eschol_publish_issue'),
    url(r'^manager/article/(?P<article_id>\d+)/publish/$', views.publish_article, name='eschol_publish_article'),

    url(r'^download/(?P<article_id>\d+)/file/(?P<file_id>\d+)/$', views.access_article_file, name='access_article_file'),
]
