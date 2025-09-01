from django.db import models
from .establishment import Establishment
from .subject import Subject

class Professor(models.Model):
    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='professors')
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)  # Hashé via set_password
    subjects = models.ManyToManyField(Subject, related_name='professors')
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name