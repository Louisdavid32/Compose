from rest_framework import viewsets, permissions
from core.models.subject import Subject
from core.serializers.subject import SubjectSerializer

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        return Subject.objects.filter(department__level__establishment=self.request.user.establishment)