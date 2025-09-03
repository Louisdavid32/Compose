# core/models/user.py
"""
Custom user & roles (multi-tenant, CEMAC phone validation)

- Email = identifiant de connexion (USERNAME_FIELD)
- Champs requis: email, full_name, phone
- Manager sécurisé (create_user / create_superuser)
- Rôles par établissement via table de jonction (UserRole)
- Plusieurs secrétaires possibles par établissement (aucune contrainte bloquante)
- Performances: index utiles, validations précoces, normalisation email

Dépendances internes:
- core/models/establishment.py : modèle Establishment (tenant)
- core/models/validators.py : validate_central_africa_phone

À configurer:
- settings.AUTH_USER_MODEL = "core.User"
- Ajouter l'app "core" dans INSTALLED_APPS

Notes migration:
- Le custom user doit exister avant la 1ère migration d'auth. Si ton projet a déjà migré,
  il faudra recréer la base ou suivre une procédure de migration contrôlée.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import models
from django.utils import timezone

from .establishment import Establishment
from .validators import validate_central_africa_phone


# -----------------------------
# Custom Manager (SOLID: SRP)
# -----------------------------
class UserManager(BaseUserManager):
    """Gestionnaire de création/normalisation des utilisateurs.

    - Normalise l'email en minuscule et supprime espaces superflus
    - Valide le téléphone (CEMAC + E.164)
    - Empêche la création de superuser sans is_staff/is_superuser
    """

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields: Any) -> "User":
        if not email:
            raise ValueError("L'email est requis.")
        email = self.normalize_email(email).strip().lower()

        full_name = (extra_fields.get("full_name") or "").strip()
        if len(full_name) < 2:
            raise ValueError("Le nom complet doit contenir au moins 2 caractères.")

        phone = (extra_fields.get("phone") or "").strip()
        if not phone:
            raise ValueError("Le numéro de téléphone est requis.")
        # Validation CEMAC + E.164
        validate_central_africa_phone(phone)

        user = self.model(email=email, full_name=full_name, phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            # Autoriser la création sans mot de passe (invitation), mais désactiver l'accès
            user.set_unusable_password()
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields: Any) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser doit avoir is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser doit avoir is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


# -----------------------------
# Custom User (SRP + least data)
# -----------------------------
class User(AbstractBaseUser, PermissionsMixin):
    """Utilisateur de la plateforme.

    - Identifiant de connexion: email (unique, normalisé)
    - Rôles liés à un établissement via UserRole (n-N)
    - Téléphone validé pour zone CEMAC (E.164)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Appartenance à un (unique) établissement (nullable pour le compte établissement lui-même)
    establishment = models.ForeignKey(
    "core.EstablishmentProfile", on_delete=models.PROTECT, null=True, blank=True,
    related_name="members",
    help_text="Établissement auquel appartient l'utilisateur (null si ESTABLISHMENT)."
    )

    email = models.EmailField(
        unique=True,
        db_index=True,
        validators=[EmailValidator()],
        help_text="Identifiant de connexion (unique)."
    )

    full_name = models.CharField(max_length=255, help_text="Nom complet affiché.")

    phone = models.CharField(
        max_length=20,
        db_index=True,
        help_text='Téléphone au format E.164 des pays CEMAC (ex: "+2376XXXXXXXX").',
    )

    # Flags standards Django
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    # Métadonnées
    date_joined = models.DateTimeField(default=timezone.now)

    # Manager
    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name", "phone"]  # demandé par create_superuser

    class Meta:
        db_table = "core_user"
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        indexes = [
            models.Index(fields=["email"], name="idx_user_email"),
            models.Index(fields=["phone"], name="idx_user_phone"),
        ]
        ordering = ["-date_joined"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.full_name} <{self.email}>"

    # Validation et normalisation côté modèle (double barrière)
    def clean(self) -> None:
        if self.email:
            self.email = self.email.strip().lower()
        if self.full_name:
            self.full_name = self.full_name.strip()
        if self.phone:
            self.phone = self.phone.strip()
            validate_central_africa_phone(self.phone)

    @property
    def display_name(self) -> str:
        return self.full_name or self.email


# ----------------------------------
# Rôles par établissement (RBAC-tenant)
# ----------------------------------
class TenantRole(models.TextChoices):
    ADMIN = "admin", "Administrateur établissement"
    TEACHER = "teacher", "Professeur"
    STUDENT = "student", "Apprenant"
    SECRETARY = "secretary", "Secrétaire"


class UserRole(models.Model):
    """Association (n-N) entre un utilisateur et un établissement avec un rôle.

    - Un utilisateur peut avoir plusieurs rôles dans un même établissement
      (ex: professeur ET secrétaire si nécessaire)
    - Plusieurs secrétaires par établissement: aucun verrou bloquant
    - Unicité protégée: (user, establishment, role) unique → pas de doublons inutiles
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="roles")

    role = models.CharField(max_length=20, choices=TenantRole.choices)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_user_role"
        verbose_name = "Rôle utilisateur"
        verbose_name_plural = "Rôles utilisateurs"
        unique_together = (("user", "establishment", "role"),)
        indexes = [
            models.Index(fields=["establishment", "role"], name="idx_role_estab_role"),
            models.Index(fields=["user"], name="idx_role_user"),
        ]
        ordering = ["establishment_id", "role", "-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user.email} @ {self.establishment.slug} [{self.get_role_display()}]"

    def clean(self) -> None:
        if not self.role:
            raise ValidationError({"role": "Le rôle est obligatoire."})

    # Helpers pratiques
    @staticmethod
    def assign(user: User, establishment: Establishment, role: str) -> "UserRole":
        """Idempotent: crée si absent, sinon retourne l'existant."""
        obj, _ = UserRole.objects.get_or_create(user=user, establishment=establishment, role=role)
        return obj

    @staticmethod
    def has_role(user: User, establishment: Establishment, role: str) -> bool:
        return UserRole.objects.filter(user=user, establishment=establishment, role=role).exists()
