"""
Modèle Establishment (Établissement / Tenant)

- Multi-tenant: chaque établissement représente un tenant porté par 'tenant_id' (UUID v4).
- Sans 'language' ni 'timezone' (supprimés comme demandé).
- Logo: champ fichier (FileField) avec validations (taille/extension).
- Données normalisées (email minuscule, website https).
- Index pour les requêtes fréquentes (type/country/city).
"""

import re
import uuid
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.template.defaultfilters import slugify

from .validators import (
    validate_file_size,
    validate_image_extension,
    validate_iso_country,
    validate_central_africa_country,   
    validate_central_africa_phone,
)


def logo_upload_path(instance, filename: str) -> str:
    """
    Chemin d'upload déterministe, partitionné par tenant pour éviter les collisions
    et faciliter l’offloading vers S3/GCS plus tard.
    """
    return f"tenants/{instance.tenant_id}/logos/{filename}"


class Establishment(models.Model):
    """
    Représente un établissement (tenant).
    """

    # --- Identité & multi-tenant ---
    tenant_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Identifiant technique global (UUID v4) du tenant."
    )

    # Liaison au compte établissement (unique)
    owner_user = models.OneToOneField(
    "core.User", on_delete=models.CASCADE, related_name="establishment_profile",
    help_text="Compte utilisateur de l'établissement (role=ESTABLISHMENT)."
    )

    
    TYPE_UNIVERSITY = "university"
    TYPE_ECOLE_SUP = "ecole_superieure"
    TYPE_INSTITUTE = "institute"
    TYPE_OTHER = "other"

    TYPE_CHOICES = (
        (TYPE_UNIVERSITY, "Université"),
        (TYPE_ECOLE_SUP, "École supérieure"),
        (TYPE_INSTITUTE, "Institut"),
        (TYPE_OTHER, "Autre"),
    )

    type = models.CharField(
        max_length=32,
        choices=TYPE_CHOICES,
        help_text="Type d’établissement."
    )

    country = models.CharField(
        max_length=2,
        help_text='Code pays ISO-3166-1 alpha-2 (ex: "CM", "FR").',
    )

    

    # Logo en tant que fichier (avec validations côté modèle)
    logo_file = models.FileField(
        upload_to=logo_upload_path,
        blank=True,
        help_text="Logo de l’établissement (fichier image).",
    )

    # Coordonnées & métadonnées publiques
    contact = models.CharField(
        max_length=20,
        blank=True,
        help_text='Téléphone au format E.164 (ex: "+2376XXXXXXXX").'
    )

    description = models.TextField(
        blank=True,
        help_text="Présentation / description (optionnel)."
    )

    region = models.CharField(
        max_length=128,
        blank=True,
        help_text="Région administrative (optionnel)."
    )

    city = models.CharField(
        max_length=128,
        blank=True,
        help_text="Ville / point d’implantation (optionnel)."
    )

    address = models.CharField(
        max_length=255,
        blank=True,
        help_text="Adresse postale (optionnel)."
    )

    website = models.URLField(
        blank=True,
        help_text="Site web institutionnel (https://...).",
        validators=[URLValidator()],
    )

    # Identifiant lisible (URL/sous-domaine)
    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text="Identifiant URL unique (généré depuis le nom si absent)."
    )

    # --- Métadonnées ---
    created_at = models.DateTimeField(auto_now_add=True, help_text="Date de création (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="Dernière mise à jour (auto).")

    class Meta:
        db_table = "core_establishment"
        verbose_name = "Établissement"
        verbose_name_plural = "Établissements"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["tenant_id"], name="idx_estab_tenant"),
            models.Index(fields=["type", "country"], name="idx_estab_type_country"),
            models.Index(fields=["country"], name="idx_estab_country"),
            models.Index(fields=["city"], name="idx_estab_city"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.country})"

    # -----------------------
    # Normalisation & sécurité
    # -----------------------
    def clean(self):
        """
        Valide et normalise avant écriture DB.
        - country    : ISO-3166-1 alpha-2 (majuscule) + restriction CEMAC
        - email      : minuscule
        - website    : ajoute https:// si schéma manquant
        - contact    : format E.164 + préfixe CEMAC
        - logo_file  : taille & extension
        """
        # Pays : ISO2 + CEMAC
        self.country = (self.country or "").upper().strip()
        validate_iso_country(self.country)            # garde la validation ISO générique
        validate_central_africa_country(self.country) # restreint aux 6 pays CEMAC

        # Email → minuscule
        if self.email:
            self.email = self.email.strip().lower()

        # Site web → forcer https si schéma manquant
        if self.website:
            w = self.website.strip()
            if not re.match(r"^https?://", w, flags=re.IGNORECASE):
                w = "https://" + w
            self.website = w

        # Téléphone : E.164 + prefix CEMAC
        if self.contact:
            validate_central_africa_phone(self.contact.strip())

        # Logo : taille + extension
        if self.logo_file:
            validate_file_size(self.logo_file, max_mb=3)
            validate_image_extension(self.logo_file)

    def save(self, *args, **kwargs):
        """
        Sauvegarde sûre :
        - Génère un slug unique à partir du nom si absent.
        - Applique les validations serveur (full_clean).
        """
        if not self.slug and self.name:
            base = slugify(self.name)[:240] or "etablissement"
            candidate = base
            i = 1
            while Establishment.objects.filter(slug=candidate).exists():
                i += 1
                candidate = f"{base}-{i}"
            self.slug = candidate

        self.full_clean()
        super().save(*args, **kwargs)
