from rest_framework import serializers
from core.models.exam import Exam

class ExamSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = Exam
        fields = ['id', 'student', 'subject', 'title', 'date', 'score', 'max_score', 'status', 'created_at', 'subject_name']
        read_only_fields = ['id', 'created_at', 'subject_name']