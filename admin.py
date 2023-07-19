from django.contrib import admin
from plugins.eschol.models import *

class JournalUnitAdmin(admin.ModelAdmin):
    fields = ['journal', 'unit', 'default_css_url', 'ezid_template']

class EscholArticleAdmin(admin.ModelAdmin):
    pass

admin.site.register(JournalUnit, JournalUnitAdmin)
admin.site.register(EscholArticle, EscholArticleAdmin)
