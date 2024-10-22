from django.contrib import admin
from plugins.eschol.models import (JournalUnit,
                                   EscholArticle,
                                   IssuePublicationHistory,
                                   ArticlePublicationHistory)

class JournalUnitAdmin(admin.ModelAdmin):
    fields = ['journal', 'unit', 'default_css_url']

class EscholArticleAdmin(admin.ModelAdmin):
    search_fields = ('article__title',)
    list_filter = ('article__journal',)
    raw_id_fields = ('article',)

class ArticlePublicationHistoryAdmin(admin.ModelAdmin):
    raw_id_fields = ('article',)

class IssuePublicationHistoryAdmin(admin.ModelAdmin):
    raw_id_fields = ('issue',)

admin.site.register(JournalUnit, JournalUnitAdmin)
admin.site.register(EscholArticle, EscholArticleAdmin)
admin.site.register(IssuePublicationHistory, IssuePublicationHistoryAdmin)
admin.site.register(ArticlePublicationHistory, ArticlePublicationHistoryAdmin)
