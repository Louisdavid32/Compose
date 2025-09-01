from django.db import models
from .department import Department

class Subject(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=[
        ('Théorique', 'Théorique'),
        ('Pratique', 'Pratique'),
        ('Mixte', 'Mixte'),
    ])
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.department.name})"