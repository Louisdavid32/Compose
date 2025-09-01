from rest_framework import serializers
from core.models.subject import Subject

class SubjectSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Subject
        fields = ['id', 'department', 'name', 'type', 'description', 'created_at', 'department_name']
        read_only_fields = ['id', 'created_at', 'department_name']