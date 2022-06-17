from django.db import models
from django.conf import settings

from journal.models import Journal
from submission.models import Article
from secrets import token_urlsafe

class JournalUnit(models.Model):
    journal = models.OneToOneField(Journal, null=True, on_delete=models.CASCADE)
    unit = models.CharField(max_length=50)

    def __str__(self):
        return "{}: {}".format(self.journal, self.unit)

class EscholArticle(models.Model):
    article = models.ForeignKey(Article)
    date_published = models.DateTimeField(auto_now=True)
    ark = models.CharField(max_length=50)

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
