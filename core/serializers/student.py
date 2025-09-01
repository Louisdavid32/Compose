from rest_framework import serializers
from core.models.student import Student
from core.models.subject import Subject  # Import the Subject model

class StudentSerializer(serializers.ModelSerializer):
    subjects = serializers.PrimaryKeyRelatedField(many=True, queryset=Subject.objects.all(), required=False)
    level_name = serializers.CharField(source='level.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Student
        fields = ['id', 'establishment', 'level', 'department', 'name', 'email', 'phone', 'address', 'birthdate', 'enrollment_date', 'status', 'subjects', 'level_name', 'department_name', 'created_at']
        read_only_fields = ['id', 'enrollment_date', 'created_at', 'level_name', 'department_name']