from django.db import models
from django.conf import settings

from journal.models import Journal
from submission.models import Article
from secrets import token_urlsafe
from django.utils.translation import gettext_lazy as _

class JournalUnit(models.Model):
    journal = models.OneToOneField(Journal, null=True, on_delete=models.CASCADE)
    unit = models.CharField(max_length=50)
    default_css_url = models.URLField(max_length=200, null=True, blank=True)
    class EzidTemplate(models.TextChoices):
        JOURNAL = 'JC', _('Journal Content')
        CHAPTER = 'BC', _('Book Chapter')

    ezid_template = models.CharField(
        max_length=2,
        choices=EzidTemplate.choices,
        default=EzidTemplate.JOURNAL,
    )
    
    def __str__(self):
        return "{}: {}".format(self.journal, self.unit)

class EscholArticle(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    date_published = models.DateTimeField(auto_now=True)
    ark = models.CharField(max_length=50)
    is_doi_registered = models.BooleanField(default=False)
    doi_result_text = models.TextField(null=True, blank=True)
    source_name = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return "{}: {}".format(str(self.article), self.ark)

    def get_short_ark(self):
        return self.ark.split("/")[-1][-8:]

    def get_eschol_url(self):
        return "{}uc/item/{}".format(settings.JSCHOL_URL, self.get_short_ark())

class AccessToken(models.Model):
    token = models.CharField(max_length=50)
    date = models.DateField(auto_now_add=True)
    article_id = models.IntegerField()
    file_id = models.IntegerField()

    def generate_token(self):
        self.token = token_urlsafe(32)
        self.save()
