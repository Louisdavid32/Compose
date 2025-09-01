from rest_framework import viewsets, permissions
from core.models.attendance import Attendance
from core.serializers.attendance import AttendanceSerializer

class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        return Attendance.objects.filter(student__establishment=self.request.user.establishment)