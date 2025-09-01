from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken
from core.models.user import User
from core.models.establishment import Establishment
from core.serializers.user import UserSerializer
from core.serializers.establishment import EstablishmentSerializer
from core.services.auth import generate_otp, verify_otp
from core.services.sms import send_sms
import uuid

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    #parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        data = request.data
        if not all([data.get(key) for key in ['institutionName', 'institutionType', 'country', 'email', 'password', 'confirmPassword', 'phoneNumber']]):
            return Response({'error': 'Veuillez remplir tous les champs obligatoires'}, status=status.HTTP_400_BAD_REQUEST)

        if data.get('password') != data.get('confirmPassword'):
            return Response({'error': 'Les mots de passe ne correspondent pas'}, status=status.HTTP_400_BAD_REQUEST)
        
        if len(data.get('password', '')) < 8:
            return Response({'error': 'Le mot de passe doit contenir au moins 8 caractères'}, status=status.HTTP_400_BAD_REQUEST)

        # Créer l’établissement (tenant_id généré par le signal)
        establishment_data = {
            'name': data.get('institutionName'),
            'type': data.get('institutionType'),
            'country': data.get('country'),
            'region': data.get('region'),
            'email': data.get('email'),
            'logo': data.get('logo'),
            'language': data.get('language', 'fr'),
            'description': data.get('description'),
            'creation_year': data.get('creation_year'),
        }
        establishment_serializer = EstablishmentSerializer(data=establishment_data)
        if establishment_serializer.is_valid():
            establishment = establishment_serializer.save()
        else:
            return Response(establishment_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Créer l’utilisateur admin (créateur)
        user_data = {
            'email': data.get('email'),
            'full_name': data.get('institutionName'),
            'establishment': establishment,
            'is_creator': True,
            'phone_number': data.get('phoneNumber'),
        }
        user = User.objects.create_user(**user_data, password=data.get('password'))
        
        # Générer et envoyer OTP pour activation
        otp = generate_otp(user, purpose='activation')
        send_sms(user.phone_number, f"Votre code OTP d’activation est : {otp}")

        return Response({
            'message': 'Compte créé avec succès. Veuillez vérifier le code OTP pour activer votre compte.',
            'user_id': user.id,
        }, status=status.HTTP_201_CREATED)


class ActivateAccountView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user_id = request.data.get('user_id')
        otp = request.data.get('otp')
        user = User.objects.filter(id=user_id).first()

        if user and verify_otp(user, otp, purpose='activation'):
            user.is_active = True
            user.save()
            return Response({'message': 'Compte activé avec succès. Vous pouvez maintenant vous connecter.'}, status=status.HTTP_200_OK)
        return Response({'error': 'Code OTP invalide ou utilisateur non trouvé'}, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        phone_number = request.data.get('phoneNumber')

        user = User.objects.filter(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                return Response({'error': 'Compte non activé. Veuillez activer votre compte.'}, status=status.HTTP_403_FORBIDDEN)
            # Générer et envoyer OTP pour 2FA
            otp = generate_otp(user, purpose='2fa')
            send_sms(phone_number, f"Votre code OTP de connexion est : {otp}")
            return Response({'message': 'Code OTP envoyé', 'user_id': user.id}, status=status.HTTP_200_OK)
        return Response({'error': 'Email ou mot de passe incorrect'}, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user_id = request.data.get('user_id')
        otp = request.data.get('otp')
        user = User.objects.filter(id=user_id).first()

        if user and verify_otp(user, otp, purpose='2fa'):
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_200_OK)
        return Response({'error': 'Code OTP invalide ou utilisateur non trouvé'}, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Déconnexion réussie'}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        user = User.objects.filter(email=email).first()
        if user:
            reset_token = str(uuid.uuid4())
            send_sms(user.phone_number, f"Votre lien de réinitialisation : http://localhost:3000/reset-password/{reset_token}")
            return Response({'message': 'Lien de réinitialisation envoyé'}, status=status.HTTP_200_OK)
        return Response({'error': 'Utilisateur non trouvé'}, status=status.HTTP_404_NOT_FOUND)

class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        new_password = request.data.get('newPassword')
        confirm_password = request.data.get('confirmPassword')

        if new_password != confirm_password:
            return Response({'error': 'Les mots de passe ne correspondent pas'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = User.objects.filter(email=email).first()
        if user:
            user.set_password(new_password)
            user.save()
            return Response({'message': 'Mot de passe réinitialisé avec succès'}, status=status.HTTP_200_OK)
        return Response({'error': 'Utilisateur non trouvé'}, status=status.HTTP_404_NOT_FOUND)

class AddAdminView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_creator:
            return Response({'error': 'Seul l’admin créateur peut ajouter des admins'}, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data
        user_data = {
            'email': data.get('email'),
            'full_name': data.get('fullName'),
            'establishment': request.user.establishment,
            'phone_number': data.get('phoneNumber'),
        }
        user = User.objects.create_user(**user_data, password=data.get('password'))
        
        # Générer et envoyer OTP pour activation
        otp = generate_otp(user, purpose='activation')
        send_sms(user.phone_number, f"Votre code OTP d’activation est : {otp}")

        return Response({'message': 'Admin ajouté avec succès. Veuillez vérifier le code OTP pour activer le compte.', 'user_id': user.id}, status=status.HTTP_201_CREATED)

