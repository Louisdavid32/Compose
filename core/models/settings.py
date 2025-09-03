"""
Modèles de configuration gérés par l'admin d'établissement.

Principes:
- Séparation des responsabilités (SOLID): Institution (profil), Notifications, Sécurité.
- OneToOne avec Establishment (1 bloc de config par tenant).
- Champs explicites + validations métier (bornes, formats).
- Indices pour accès lecture fréquent.
"""

from django.core.exceptions import ValidationError
from django.db import models
from .establishment import Establishment


class InstitutionSettings(models.Model):
    """
    Paramètres d'identité complétant l'établissement (branding & préférences d'affichage).
    NB: On garde ici uniquement ce qui n'est pas au cœur du modèle Establishment.
    """
    establishment = models.OneToOneField(
        Establishment,
        on_delete=models.CASCADE,
        related_name="institution_settings",
        help_text="Lien 1–1 avec l’établissement (tenant)."
    )

    # Exemple de préférences UI/branding (optionnelles, évolutives)
    primary_color = models.CharField(
        max_length=9, blank=True,
        help_text="Couleur principale (hex, ex: #3178c6)."
    )
    secondary_color = models.CharField(
        max_length=9, blank=True,
        help_text="Couleur secondaire (hex)."
    )
    email_signature = models.TextField(
        blank=True,
        help_text="Signature par défaut pour les communications institutionnelles."
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_institution_settings"
        verbose_name = "Paramètres d’institution"
        verbose_name_plural = "Paramètres d’institution"
        indexes = [models.Index(fields=["establishment"], name="idx_inst_set_estab")]

    def __str__(self) -> str:
        return f"InstitutionSettings<{self.establishment.slug}>"


class NotificationSettings(models.Model):
    """
    Paramètres de notifications (emails, etc.).
    Aligne les champs avec l’UI (welcome/result/reminder/marketing + footer).
    """
    establishment = models.OneToOneField(
        Establishment,
        on_delete=models.CASCADE,
        related_name="notification_settings",
        help_text="Lien 1–1 avec l’établissement (tenant)."
    )

    email_notifications = models.BooleanField(default=True, help_text="Activer l’envoi d’emails.")
    welcome_email = models.BooleanField(default=True, help_text="Envoyer l’email de bienvenue.")
    result_email = models.BooleanField(default=True, help_text="Notifier la publication des résultats.")
    reminder_email = models.BooleanField(default=True, help_text="Envoyer des rappels avant une évaluation.")
    marketing_email = models.BooleanField(default=False, help_text="Envoyer des emails marketing/produit.")
    email_footer = models.TextField(blank=True, help_text="Signature/mention légale en bas des emails.")

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_notification_settings"
        verbose_name = "Paramètres de notifications"
        verbose_name_plural = "Paramètres de notifications"
        indexes = [models.Index(fields=["establishment"], name="idx_notif_set_estab")]

    def __str__(self) -> str:
        return f"NotificationSettings<{self.establishment.slug}>"


class SecuritySettings(models.Model):
    """
    Paramètres de sécurité (2FA, politique MDP, session, restriction IP).
    """
    POLICY_LOW = "low"
    POLICY_MEDIUM = "medium"
    POLICY_HIGH = "high"
    POLICY_CHOICES = (
        (POLICY_LOW, "Basique (6+)"),
        (POLICY_MEDIUM, "Moyenne (8+, lettres & chiffres)"),
        (POLICY_HIGH, "Élevée (10+, lettres/chiffres/symboles)"),
    )

    establishment = models.OneToOneField(
        Establishment,
        on_delete=models.CASCADE,
        related_name="security_settings",
        help_text="Lien 1–1 avec l’établissement (tenant)."
    )

    two_factor_auth = models.BooleanField(default=False, help_text="Exiger la 2FA pour les admins.")
    password_policy = models.CharField(
        max_length=10,
        choices=POLICY_CHOICES,
        default=POLICY_MEDIUM,
        help_text="Niveau minimal de complexité des mots de passe."
    )
    session_timeout_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Expiration des sessions (minutes). 5 à 1440."
    )
    ip_restriction = models.BooleanField(
        default=False,
        help_text="Activer la restriction d’accès par IP."
    )
    allowed_ip_ranges = models.JSONField(
        default=list, blank=True,
        help_text='Liste de plages IP autorisées (CIDR), ex: ["192.168.1.0/24", "10.0.0.1/32"].'
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_security_settings"
        verbose_name = "Paramètres de sécurité"
        verbose_name_plural = "Paramètres de sécurité"
        indexes = [models.Index(fields=["establishment"], name="idx_sec_set_estab")]

    def __str__(self) -> str:
        return f"SecuritySettings<{self.establishment.slug}>"

    # Garde-fous métier
    def clean(self):
        """
        Valide les bornes et formats de sécurité:
        - session_timeout_minutes: entre 5 et 1440
        - allowed_ip_ranges: liste de chaînes non vides (validation CIDR fine à faire côté service si besoin)
        """
        if not (5 <= int(self.session_timeout_minutes) <= 1440):
            raise ValidationError({"session_timeout_minutes": "Doit être compris entre 5 et 1440 minutes."})

        if self.ip_restriction:
            if not isinstance(self.allowed_ip_ranges, list) or not self.allowed_ip_ranges:
                raise ValidationError({"allowed_ip_ranges": "Fournir au moins une plage IP en mode restriction."})
            # Vérif basique (non vide). Une validation CIDR stricte peut être ajoutée au niveau service.
            for cidr in self.allowed_ip_ranges:
                if not isinstance(cidr, str) or not cidr.strip():
                    raise ValidationError({"allowed_ip_ranges": "Chaque entrée doit être une chaîne CIDR non vide."})
