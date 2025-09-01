from rest_framework import serializers
from core.models.level import Level

class LevelSerializer(serializers.ModelSerializer):
    departments_count = serializers.IntegerField(read_only=True)
    students_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Level
        fields = ['id', 'establishment', 'name', 'description', 'created_at', 'departments_count', 'students_count']
        read_only_fields = ['id', 'created_at', 'departments_count', 'students_count']