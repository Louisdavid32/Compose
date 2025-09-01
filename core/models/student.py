from django.db import models
from .establishment import Establishment
from .level import Level
from .department import Department
from .subject import Subject

class Student(models.Model):
    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='students')
    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name='students')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='students')
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)  # Hashé via set_password
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    birthdate = models.DateField(blank=True, null=True)
    enrollment_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[
        ('Actif', 'Actif'),
        ('Inactif', 'Inactif'),
    ], default='Actif')
    subjects = models.ManyToManyField(Subject, related_name='students')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name