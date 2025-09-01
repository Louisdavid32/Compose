# core/serializers/user.py
from rest_framework import serializers
from core.models.user import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'establishment', 'is_active', 'is_creator', 'phone_number']
        read_only_fields = ['id', 'is_creator']