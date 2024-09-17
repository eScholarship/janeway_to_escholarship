from secrets import token_urlsafe

from django.db import models
from django.conf import settings

from journal.models import Journal
from submission.models import Article

class JournalUnit(models.Model):
    journal = models.OneToOneField(Journal, null=True, on_delete=models.CASCADE)
    unit = models.CharField(max_length=50)
    default_css_url = models.URLField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"{self.journal}: {self.unit}"

class EscholArticle(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    date_published = models.DateTimeField(auto_now=True)
    ark = models.CharField(max_length=50)
    is_doi_registered = models.BooleanField(default=False)
    doi_result_text = models.TextField(null=True, blank=True)
    source_name = models.CharField(max_length=20, null=True, blank=True)
    source_id = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"{self.article}: {self.ark}"

    def get_short_ark(self):
        return self.ark.rsplit("/", maxsplit=1)[-1][2:]

    def get_eschol_url(self):
        return f"{settings.JSCHOL_URL}uc/item/{self.get_short_ark()}"

    def has_doi_error(self):
        rtext = self.doi_result_text
        return not (self.is_doi_registered and ("success" in rtext or not rtext))

class AccessToken(models.Model):
    token = models.CharField(max_length=50)
    date = models.DateField(auto_now_add=True)
    article_id = models.IntegerField()
    file_id = models.IntegerField()

    def generate_token(self):
        self.token = token_urlsafe(32)
        self.save()

class ArticlePublicationHistory(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    article = models.ForeignKey('submission.Article', on_delete=models.CASCADE)
    issue_pub = models.ForeignKey('IssuePublicationHistory',
                                  blank=True,
                                  null=True,
                                  on_delete=models.CASCADE)
    success = models.BooleanField()
    result = models.TextField(null=True, blank=True)

    def get_doi_error(self):
        e = EscholArticle.objects.filter(article=self.article)
        if e.exists():
            a = e.first()
            if a.has_doi_error():
                return a.doi_result_text
        return False

    def __str__(self):
        success = "successful" if self.success else "failed"
        s = f"{self.article} publication {success} on {self.date}"
        if self.issue_pub:
            s += f" with {self.issue_pub.issue}"
        return s

    class Meta:
        ordering = ['-date']

class IssuePublicationHistory(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    issue = models.ForeignKey('journal.Issue', on_delete=models.CASCADE)
    success = models.BooleanField(default=False)
    is_complete = models.BooleanField(default=False)
    result = models.TextField(null=True, blank=True)

    def result_text(self):
        if self.is_complete:
            total_success = self.articlepublicationhistory_set.filter(success=True).count()
            total = self.articlepublicationhistory_set.all().count()
            return f"Successfully published {total_success} of {total} articles"

        return "Publication in process"

    def __str__(self):
        if self.is_complete:
            ts = self.articlepublicationhistory_set.filter(success=True).count()
            t = self.articlepublicationhistory_set.all().count()
            s = "successful" if self.success else "failed"

            return f"{self.issue} publication {s} on {self.date}: {ts} of {t} articles published."

        return f"{self.issue} publication in process"

    class Meta:
        ordering = ['-date']
