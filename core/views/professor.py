from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from core.models.professor import Professor
from django.db.models import Q
from core.serializers.professor import ProfessorSerializer
from core.services.auth import generate_otp
from core.services.sms import send_sms
from django.contrib.auth.hashers import make_password

class ProfessorViewSet(viewsets.ModelViewSet):
    queryset = Professor.objects.all()
    serializer_class = ProfessorSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        queryset = Professor.objects.filter(establishment=self.request.user.establishment)
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(email__icontains=search) |
                Q(subjects__name__icontains=search) | Q(subjects__department__name__icontains=search)
            ).distinct()
        return queryset

    def perform_create(self, serializer):
        professor = serializer.save(establishment=self.request.user.establishment)
        professor.password = make_password(professor.password)
        professor.save()
        otp = generate_otp(professor, purpose='activation')
        send_sms(professor.email, f"Votre code OTP d’activation est : {otp}")

    def perform_update(self, serializer):
        professor = serializer.save()
        if 'password' in self.request.data:
            professor.password = make_password(self.request.data['password'])
            professor.save()

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        professor = self.get_object()
        otp = generate_otp(professor, purpose='password_reset')
        send_sms(professor.email, f"Votre lien de réinitialisation : http://localhost:3000/reset-password/{otp}")
        return Response({'message': 'Lien de réinitialisation envoyé'})