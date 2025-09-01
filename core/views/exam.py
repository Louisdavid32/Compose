from rest_framework import viewsets, permissions
from core.models.exam import Exam
from core.serializers.exam import ExamSerializer

class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        return Exam.objects.filter(student__establishment=self.request.user.establishment)
    