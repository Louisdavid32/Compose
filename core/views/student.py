from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from core.models.student import Student
from core.models.department import Department  # Import the Department model
from core.models.level import Level  # Import the Level model
from core.serializers.student import StudentSerializer
from core.serializers.exam import ExamSerializer
from core.serializers.attendance import AttendanceSerializer
from core.services.auth import generate_otp
from core.services.sms import send_sms
from django.contrib.auth.hashers import make_password
from django.db.models import Q
import csv
from rest_framework.parsers import MultiPartParser

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        queryset = Student.objects.filter(establishment=self.request.user.establishment)
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(email__icontains=search) |
                Q(level__name__icontains=search) | Q(department__name__icontains=search)
            ).distinct()
        return queryset

    def perform_create(self, serializer):
        student = serializer.save(establishment=self.request.user.establishment)
        student.password = make_password(student.password)
        student.save()
        otp = generate_otp(student, purpose='activation')
        send_sms(student.email, f"Votre code OTP d’activation est : {otp}")

    def perform_update(self, serializer):
        student = serializer.save()
        if 'password' in self.request.data:
            student.password = make_password(self.request.data['password'])
            student.save()

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        student = self.get_object()
        otp = generate_otp(student, purpose='password_reset')
        send_sms(student.email, f"Votre lien de réinitialisation : http://localhost:3000/reset-password/{otp}")
        return Response({'message': 'Lien de réinitialisation envoyé'})

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def import_csv(self, request):
        file = request.FILES.get('file')
        if not file.name.endswith('.csv'):
            return Response({'error': 'Fichier CSV requis'}, status=400)
        
        decoded_file = file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        for row in reader:
            try:
                level = Level.objects.get(name=row['level'], establishment=request.user.establishment)
                department = Department.objects.get(name=row['department'], level=level)
                student_data = {
                    'establishment': request.user.establishment,
                    'level': level,
                    'department': department,
                    'name': row['name'],
                    'email': row['email'],
                    'password': make_password(row['password']),
                    'phone': row.get('phone', ''),
                    'address': row.get('address', ''),
                    'birthdate': row.get('birthdate', None),
                    'status': row.get('status', 'Actif'),
                }
                student = Student(**student_data)
                student.save()
                otp = generate_otp(student, purpose='activation')
                send_sms(student.email, f"Votre code OTP d’activation est : {otp}")
            except Exception as e:
                continue
        return Response({'message': 'Importation réussie'}, status=200)

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        import io
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="students.csv"'

        writer = csv.writer(response)
        writer.writerow(['name', 'email', 'phone', 'address', 'birthdate', 'level', 'department', 'status'])
        for student in Student.objects.filter(establishment=request.user.establishment):
            writer.writerow([
                student.name,
                student.email,
                student.phone or '',
                student.address or '',
                student.birthdate or '',
                student.level.name,
                student.department.name,
                student.status,
            ])
        return response

    @action(detail=True, methods=['get'])
    def details(self, request, pk=None):
        student = self.get_object()
        exams = Exam.objects.filter(student=student)
        attendances = Attendance.objects.filter(student=student)
        subjects = student.subjects.all()

        student_serializer = StudentSerializer(student)
        exams_serializer = ExamSerializer(exams, many=True)
        attendances_serializer = AttendanceSerializer(attendances, many=True)
        subjects_serializer = SubjectSerializer(subjects, many=True)

        return Response({
            'student': student_serializer.data,
            'exams': exams_serializer.data,
            'attendances': attendances_serializer.data,
            'subjects': subjects_serializer.data,
        })