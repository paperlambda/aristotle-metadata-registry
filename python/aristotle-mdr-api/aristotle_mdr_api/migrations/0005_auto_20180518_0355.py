# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-05-18 03:55
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aristotle_mdr_api', '0004_auto_20180518_0354'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aristotletoken',
            name='key',
            field=models.CharField(max_length=40, unique=True, verbose_name='Key'),
        ),
    ]
