from django.db import models
from .student import Student
from .subject import Subject

class Exam(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exams')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exams')
    title = models.CharField(max_length=255)
    date = models.DateField()
    score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(default=20)
    status = models.CharField(max_length=20, choices=[
        ('Planifié', 'Planifié'),
        ('En cours', 'En cours'),
        ('Terminé', 'Terminé'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.subject.name})"