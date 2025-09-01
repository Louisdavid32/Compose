from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views.auth import RegisterView, LoginView, VerifyOTPView, AddAdminView, ActivateAccountView, PasswordResetConfirmView,PasswordResetRequestView, LogoutView
from core.views.establishment import EstablishmentViewSet
from core.views.level import LevelViewSet
from core.views.department import DepartmentViewSet
from core.views.subject import SubjectViewSet
from core.views.professor import ProfessorViewSet
from core.views.student import StudentViewSet
from core.views.exam import ExamViewSet
from core.views.attendance import AttendanceViewSet
from rest_framework_simplejwt.views import TokenRefreshView

router = DefaultRouter()
router.register(r'establishments', EstablishmentViewSet)
router.register(r'levels', LevelViewSet)
router.register(r'departments', DepartmentViewSet)
router.register(r'subjects', SubjectViewSet)
router.register(r'professors', ProfessorViewSet)
router.register(r'students', StudentViewSet)
router.register(r'exams', ExamViewSet)
router.register(r'attendances', AttendanceViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
    path('activate/', ActivateAccountView.as_view(), name='activate'),
    path('login/', LoginView.as_view(), name='login'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('add-admin/', AddAdminView.as_view(), name='add_admin'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]