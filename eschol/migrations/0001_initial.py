# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2022-05-23 19:23
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('submission', '0067_auto_20220321_1306'),
        ('journal', '0050_issue_last_modified'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(max_length=50)),
                ('date', models.DateField(auto_now_add=True)),
                ('article_id', models.IntegerField()),
                ('file_id', models.IntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='EscholArticle',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_published', models.DateTimeField(auto_now=True)),
                ('ark', models.CharField(max_length=50)),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='submission.Article')),
            ],
        ),
        migrations.CreateModel(
            name='JournalUnit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('unit', models.CharField(max_length=20)),
                ('journal', models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, to='journal.Journal')),
            ],
        ),
    ]
