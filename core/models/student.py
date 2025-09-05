# core/models/student.py
"""
StudentProfile (profil d'étudiant) — Multi-tenant, performant, prêt prod
========================================================================
Option A retenue : **la source de vérité du parcours est la FILIÈRE (Program)**

Objectifs (exigences respectées)
--------------------------------
- ZÉRO duplication : on **supprime** department/level du modèle étudiant.
  → On expose `department` et `level` via des **propriétés** lisant `student.program`.
- Multi-tenant strict : chaque StudentProfile appartient à **UN** établissement (tenant).
- Intégrité métier :
  - `user.role == "student"`
  - `user.establishment == student.establishment`
  - `program.establishment == student.establishment`
  - `current_school_year` valide ("YYYY-YYYY"), `date_of_birth` non future,
    téléphones parents au format E.164 **CEMAC** (si fournis).
  - `matricule` **unique par établissement** (clé métier).
- Performance :
  - Index ciblés : `(establishment, program)`, `(establishment, current_school_year)`, `(establishment, matricule)`.
  - Accès rapide au tenant via `tenant_id`.
- Sécurité & robustesse :
  - `on_delete=PROTECT` pour éviter des orphelins côté établissement/programme.
  - `save()` applique `full_clean()` (validation serveur systématique).
- SOLID :
  - Responsabilités claires (validation métier dans `clean()`),
  - Aucune logique de mapping externe cachée,
  - Propriétés en lecture seule pour department/level (dérivés de program).

Champs pris en compte
---------------------
- user : OneToOne(User) — le compte de l'étudiant (identité sur User : email/nom/tel)
- establishment : FK(EstablishmentProfile) — tenant possesseur de l'étudiant
- program : FK(Program) — **filière suivie (obligatoire)**, porte department & level
- matricule : identifiant scolaire **unique par établissement**
- current_school_year : année scolaire en cours (ex: "2025-2026")
- date_of_birth : date de naissance
- parent_name_1 / parent_phone_1 : parent/tuteur 1 (téléphone CEMAC optionnel)
- parent_name_2 / parent_phone_2 : parent/tuteur 2 (téléphone CEMAC optionnel)
- address : adresse de résidence (optionnelle)
- created_at / updated_at : timestamps

Remarques
---------
- `department` et `level` **ne sont pas stockés** ici pour éviter les divergences.
  Utiliser `student.department` et `student.level` (propriétés) qui lisent `student.program`.
"""

from __future__ import annotations

import uuid
from typing import Optional, TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models.user import User
from core.models.establishment import Establishment
from core.models.program import Program
from core.models.validators import (
    validate_central_africa_phone,
    validate_school_year,
)

if TYPE_CHECKING:  # Types uniquement (évite les imports circulaires à l'exécution)
    from core.models.department import Department
    from core.models.level import Level


class StudentProfile(models.Model):
    """
    Profil d'étudiant (par tenant), rattaché à un User(role='student') et à une filière (Program).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 1—1 avec l'utilisateur étudiant (identité sur User)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        help_text="Compte utilisateur de l'étudiant (doit avoir role='student').",
    )

    # Scoping tenant explicite (FK → filtres/index rapides)
    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="students",
        help_text="Établissement (tenant) ; doit égaler user.establishment.",
    )

    # FILIÈRE suivie = source de vérité du parcours (porte department & level)
    program = models.ForeignKey(
        Program,
        on_delete=models.PROTECT,
        related_name="students",
        help_text="Filière suivie par l'étudiant (doit appartenir au même établissement).",
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
            # Filtres fréquents : par tenant + filière / année
            models.Index(fields=["establishment", "program"], name="idx_student_estab_program"),
            models.Index(fields=["establishment", "current_school_year"], name="idx_student_estab_year"),
            # Accès matricule rapide par tenant (utile lors d'import/commit)
            models.Index(fields=["establishment", "matricule"], name="idx_student_estab_matricule"),
        ]
        ordering = ["-created_at"]

    # ---------- Propriétés dérivées (lecture seule, anti-duplication) ----------

    @property
    def department(self) -> Optional["Department"]:
        """
        Département dérivé de la filière (Program).
        Retourne None si program n'est pas renseigné (cas limite).
        """
        return getattr(self.program, "department", None)

    @property
    def level(self) -> Optional["Level"]:
        """
        Niveau dérivé de la filière (Program).
        Retourne None si program n'est pas renseigné (cas limite).
        """
        return getattr(self.program, "level", None)

    @property
    def tenant_id(self):
        """Accès direct au tenant pour logs/exports/caches."""
        return self.establishment.tenant_id

    # ---------- Intégrité & Sécurité ----------

    def clean(self):
        """
        Valide l'intégrité métier et multi-tenant avant écriture DB.
        """
        # 1) User doit être un student
        if self.user.role != "student":
            raise ValidationError({"user": "Le user lié doit avoir le rôle 'student'."})

        # 2) Cohérence d'appartenance (User.establishment == StudentProfile.establishment)
        if not self.user.establishment_id or self.user.establishment_id != self.establishment_id:
            raise ValidationError({"establishment": "Doit égaler user.establishment."})

        # 3) Filière (Program) dans le même établissement
        if self.program and self.program.establishment_id != self.establishment_id:
            raise ValidationError({"program": "La filière doit appartenir au même établissement (tenant)."})

        # 4) Année scolaire courante valide
        validate_school_year(self.current_school_year)

        # 5) Date de naissance plausible (pas dans le futur)
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError({"date_of_birth": "La date de naissance ne peut pas être future."})

        # 6) Téléphones parents (optionnels → valider si présents)
        if self.parent_phone_1:
            validate_central_africa_phone(self.parent_phone_1)
        if self.parent_phone_2:
            validate_central_africa_phone(self.parent_phone_2)

        # 7) (Optionnel informatif) Cohérence hiérarchique dérivée
        #    Si vos modèles Program garantissent déjà:
        #      - program.department.establishment == establishment
        #      - program.level.establishment == establishment
        #    alors rien de plus à vérifier ici.

    def save(self, *args, **kwargs):
        # Validation complète avant écriture DB (sécurité)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.full_name} [{self.matricule}] — {self.current_school_year}"
