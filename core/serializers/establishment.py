from rest_framework import serializers
from core.models.establishment import Establishment

class EstablishmentSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(required=False, allow_null=True)
    class Meta:
        model = Establishment
        fields = ['id', 'name', 'type', 'country', 'region', 'address', 'phone', 'website', 'email', 'logo', 'language', 'description', 'created_at', 'creation_year', 'tenant_id']
        read_only_fields = ['id', 'created_at', 'tenant_id']