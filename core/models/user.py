# core/models/user.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from .establishment import Establishment

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('L’email est requis')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', False)  # Compte inactif par défaut
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_creator', True)
        extra_fields.setdefault('is_active', True)  # Superutilisateur actif
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    establishment = models.ForeignKey('Establishment', on_delete=models.CASCADE, related_name='admins', null=True)
    is_active = models.BooleanField(default=False)  # Compte inactif jusqu'à activation
    is_staff = models.BooleanField(default=False)
    is_creator = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.email})"
        
    class Meta:
        indexes = [
            models.Index(fields=['email']),
        ]