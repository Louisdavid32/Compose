from rest_framework import serializers
from core.models.department import Department

class DepartmentSerializer(serializers.ModelSerializer):
    level_name = serializers.CharField(source='level.name', read_only=True)

    class Meta:
        model = Department
        fields = ['id', 'level', 'name', 'description', 'created_at', 'level_name']
        read_only_fields = ['id', 'created_at', 'level_name']