from rest_framework import serializers
from core.models.attendance import Attendance

class AttendanceSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'student', 'subject', 'date', 'status', 'created_at', 'subject_name']
        read_only_fields = ['id', 'created_at', 'subject_name']