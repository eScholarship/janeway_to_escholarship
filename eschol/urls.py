from django.conf.urls import url

from plugins.eschol import views


urlpatterns = [
    url(r'^manager/$', views.eschol_manager, name='eschol_manager'),
    url(r'^download/(?P<article_id>\d+)/file/(?P<file_id>\d+)/$', views.access_article_file, name='access_article_file'),
]
