from rest_framework import viewsets, permissions
from core.models.department import Department
from core.serializers.department import DepartmentSerializer

class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        return Department.objects.filter(level__establishment=self.request.user.establishment)