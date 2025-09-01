from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from core.models.establishment import Establishment
from core.serializers.establishment import EstablishmentSerializer

class EstablishmentViewSet(viewsets.ModelViewSet):
    queryset = Establishment.objects.all()
    serializer_class = EstablishmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]  # Pour gérer les uploads de fichiers (ex. logo)

    def get_queryset(self):
        # Filtrage par tenant_id pour respecter la multi-tenancy
        return Establishment.objects.filter(tenant_id=self.request.user.establishment.tenant_id)

    def update(self, request, *args, **kwargs):
        # Restriction aux admins créateurs
        if not request.user.is_creator:
            return Response(
                {'error': 'Seul l’admin créateur peut modifier l’établissement'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        # Assurer que l'établissement est lié au tenant_id de l'utilisateur
        serializer.save(tenant_id=self.request.user.establishment.tenant_id)

    def perform_update(self, serializer):
        # Validation supplémentaire pour les mises à jour
        serializer.save()

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def current(self, request):
        # Récupérer l'établissement actuel de l'utilisateur connecté
        try:
            establishment = Establishment.objects.get(tenant_id=self.request.user.establishment.tenant_id)
            serializer = self.get_serializer(establishment)
            return Response(serializer.data)
        except Establishment.DoesNotExist:
            return Response(
                {'error': 'Établissement non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )