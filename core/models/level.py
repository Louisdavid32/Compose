from django.db import models
from .establishment import Establishment

class Level(models.Model):
    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='levels')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.establishment.name})"

    @property
    def departments_count(self):
        return self.departments.count()

    @property
    def students_count(self):
        return self.students.count()