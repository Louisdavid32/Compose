"""
StudentProfile (profil d'étudiant) — Multi-tenant & SOLID

But
---
- Étend les infos du User 'student' sans dupliquer l'identité (email/nom/tel sont sur User).
- Garantit l'appartenance à UN établissement (tenant), cohérente avec user.establishment.
- Matricule **unique par établissement** (clé métier).
- Ajoute l'**année scolaire en cours** (validation stricte "YYYY-YYYY").

Perf & Sécurité
---------------
- Index sur (establishment, level) / (establishment, department) / (establishment, current_school_year).
- Validations CEMAC sur téléphones parents (si fournis).
- `on_delete=PROTECT` pour éviter des données orphelines.
"""

import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models.user import User
from core.models.establishment import Establishment
from core.models.validators import (
    validate_central_africa_phone,
    validate_school_year,
)


class StudentProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 1—1 avec le User qui a role='student'
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        help_text="Compte utilisateur de l'étudiant (doit avoir role='student').",
    )

    # Scoping tenant (FK explicite pour filtres/index rapides)
    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="students",
        help_text="Établissement (tenant) ; doit égaler user.establishment.",
    )

    # Clé métier (unique par établissement)
    matricule = models.CharField(
        max_length=50,
        help_text="Identifiant scolaire, **unique** à l'échelle de l'établissement.",
    )

    # Année scolaire en cours (valide: '2024-2025', '2025-2026', ...)
    current_school_year = models.CharField(
        max_length=9,
        help_text='Année scolaire en cours (format "YYYY-YYYY").',
    )

    # Informations personnelles
    date_of_birth = models.DateField(help_text="Date de naissance (YYYY-MM-DD).")

    parent_name_1 = models.CharField(max_length=255, blank=True, help_text="Parent/tuteur 1.")
    parent_phone_1 = models.CharField(max_length=20, blank=True, help_text="Téléphone parent/tuteur 1 (CEMAC).")
    parent_name_2 = models.CharField(max_length=255, blank=True, help_text="Parent/tuteur 2.")
    parent_phone_2 = models.CharField(max_length=20, blank=True, help_text="Téléphone parent/tuteur 2 (CEMAC).")

    address = models.CharField(max_length=255, blank=True, help_text="Adresse de résidence (optionnel).")

    # Parcours (suppose que Level/Department existent ; idéalement scopés par établissement)
    level = models.ForeignKey(
        "core.Level",
        on_delete=models.PROTECT,
        related_name="students",
        help_text="Niveau académique actuel.",
    )
    department = models.ForeignKey(
        "core.Department",
        on_delete=models.PROTECT,
        related_name="students",
        help_text="Filière / département de l'étudiant.",
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_student_profile"
        verbose_name = "Profil étudiant"
        verbose_name_plural = "Profils étudiants"
        constraints = [
            # Unicité du matricule **par établissement**
            models.UniqueConstraint(
                fields=["establishment", "matricule"],
                name="uq_student_matricule_per_establishment",
            )
        ]
        indexes = [
            models.Index(fields=["establishment", "level"], name="idx_student_estab_level"),
            models.Index(fields=["establishment", "department"], name="idx_student_estab_dept"),
            models.Index(fields=["establishment", "current_school_year"], name="idx_student_estab_year"),
        ]
        ordering = ["-created_at"]

    # ---------- Helpers perf ----------
    @property
    def tenant_id(self):
        """Accès direct au tenant pour logs/exports/caches."""
        return self.establishment.tenant_id

    # ---------- Intégrité & Sécurité ----------
    def clean(self):
        # 1) User doit être un student
        if self.user.role != "student":
            raise ValidationError({"user": "Le user lié doit avoir le rôle 'student'."})

        # 2) Cohérence d'appartenance (User.establishment == StudentProfile.establishment)
        if not self.user.establishment_id or self.user.establishment_id != self.establishment_id:
            raise ValidationError({"establishment": "Doit égaler user.establishment."})

        # 3) Année scolaire courante valide
        validate_school_year(self.current_school_year)

        # 4) Date de naissance plausible (pas dans le futur)
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError({"date_of_birth": "La date de naissance ne peut pas être future."})

        # 5) Téléphones parents (optionnels → valider si présents)
        if self.parent_phone_1:
            validate_central_africa_phone(self.parent_phone_1)
        if self.parent_phone_2:
            validate_central_africa_phone(self.parent_phone_2)

        # 6) (Optionnel) Cohérence tenant pour Level/Department si ces modèles sont scopés par établissement
        for ref_name, ref in (("level", self.level), ("department", self.department)):
            est_id = getattr(ref, "establishment_id", None) or getattr(ref, "establishment_id", None)
            if est_id and est_id != self.establishment_id:
                raise ValidationError({ref_name: "Doit appartenir au même établissement (tenant)."})

    def save(self, *args, **kwargs):
        # Validation complète avant écriture DB (sécurité)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.full_name} [{self.matricule}] — {self.current_school_year}"
