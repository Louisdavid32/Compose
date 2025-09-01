from django.db import models
from .student import Student
from .subject import Subject

class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    status = models.CharField(max_length=20, choices=[
        ('Présent', 'Présent'),
        ('Absent', 'Absent'),
        ('Retard', 'Retard'),
        ('Justifié', 'Justifié'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.name} - {self.subject.name} ({self.date})"