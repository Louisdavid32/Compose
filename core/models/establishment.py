# core/models/establishment.py
from django.db import models
import uuid

class Establishment(models.Model):
    TYPE_CHOICES = (
        ('university', 'Université'),
        ('school', 'École supérieure'),
        ('institute', 'Institut'),
        ('other', 'Autre'),
    )

    name = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    country = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(unique=True)
    website = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    language = models.CharField(max_length=10, default='fr')
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    creation_year = models.PositiveIntegerField(null=True, blank=True)
    tenant_id = models.UUIDField(unique=True, editable=False, default=None)  # UUID généré par signal

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'establishments'
        indexes = [
            models.Index(fields=['tenant_id']),
        ]

#
       
"""class Evaluation(models.Model):
    id = models.UUIDField(primary_key=True)
    title = models.CharField(max_length=255)
    ec_id = models.UUIDField()
    type = models.CharField(max_length=50)
    duration = models.IntegerField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    instructions = models.TextField()
    status = models.CharField(max_length=20)"""