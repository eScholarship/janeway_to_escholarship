from django.contrib import admin
from plugins.eschol.models import *

class JournalUnitAdmin(admin.ModelAdmin):
    fields = ['journal', 'unit', 'default_css_url']

class EscholArticleAdmin(admin.ModelAdmin):
    search_fields = ('article__title',)
    list_filter = ('article__journal',)
    raw_id_fields = ('article',)

class ArticlePublicationHistoryAdmin(admin.ModelAdmin):
    pass

class IssuePublicationHistoryAdmin(admin.ModelAdmin):
    pass

admin.site.register(JournalUnit, JournalUnitAdmin)
admin.site.register(EscholArticle, EscholArticleAdmin)
admin.site.register(IssuePublicationHistory, IssuePublicationHistoryAdmin)
admin.site.register(ArticlePublicationHistory, ArticlePublicationHistoryAdmin)