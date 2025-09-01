from rest_framework import serializers
from core.models.professor import Professor
from core.models.subject import Subject

class ProfessorSerializer(serializers.ModelSerializer):
    subjects = serializers.PrimaryKeyRelatedField(many=True, queryset=Subject.objects.all())
    department = serializers.CharField(source='subjects.first.department.name', read_only=True)

    class Meta:
        model = Professor
        fields = ['id', 'establishment', 'name', 'email', 'subjects', 'department', 'is_active', 'created_at']
        read_only_fields = ['id', 'is_active', 'created_at', 'department']