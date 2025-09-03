"""
TeacherProfile (profil professeur) — Multi-tenant & SOLID

But
---
- Étend le User 'teacher' sans dupliquer l'identité (email/nom/tel sont sur User).
- Garantit l'appartenance à UN établissement (tenant).
- Ajoute l'**année scolaire en cours** (format "YYYY-YYYY").
- Associe les **matières** et **niveaux** via tables pivot *with-tenant* (contrôle d’intégrité).

Perf & Sécurité
---------------
- Index sur establishment (filtrage massif par tenant).
- Unicité des liaisons (teacher, subject) et (teacher, level).
- Nettoyage strict: tout objet lié (subject/level) doit être du **même établissement**.
"""

import uuid
from django.core.exceptions import ValidationError
from django.db import models

from core.models.user import User
from core.models.establishment import Establishment
from core.models.validators import validate_school_year


class TeacherProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        help_text="Compte utilisateur du professeur (doit avoir role='teacher').",
    )

    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="teachers",
        help_text="Établissement (tenant) ; doit égaler user.establishment.",
    )

    current_school_year = models.CharField(
        max_length=9,
        help_text='Année scolaire en cours (format "YYYY-YYYY").',
    )

    # Optionnel: bio/grade etc.
    bio = models.TextField(blank=True)

    # M2M via tables pivot (contrôle tenant explicite)
    subjects = models.ManyToManyField(
        "core.Subject",
        through="TeacherSubject",
        related_name="teacher_set",
        blank=True,
        help_text="Matières enseignées.",
    )
    levels = models.ManyToManyField(
        "core.Level",
        through="TeacherLevel",
        related_name="teacher_set",
        blank=True,
        help_text="Niveaux enseignés.",
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_teacher_profile"
        verbose_name = "Profil professeur"
        verbose_name_plural = "Profils professeurs"
        indexes = [models.Index(fields=["establishment"], name="idx_teacher_estab")]
        ordering = ["-created_at"]

    # ---------- Helpers perf ----------
    @property
    def tenant_id(self):
        return self.establishment.tenant_id

    # ---------- Intégrité & Sécurité ----------
    def clean(self):
        if self.user.role != "teacher":
            raise ValidationError({"user": "Le user lié doit avoir le rôle 'teacher'."})
        if not self.user.establishment_id or self.user.establishment_id != self.establishment_id:
            raise ValidationError({"establishment": "Doit égaler user.establishment."})
        validate_school_year(self.current_school_year)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.full_name} @ {self.establishment.slug} — {self.current_school_year}"


# ---------- Tables pivot (intègrent l'établissement pour scoping/indices) ----------

class TeacherSubject(models.Model):
    """
    Liaison Professeur ↔ Matière.
    - Unicité (teacher, subject)
    - Contrôle d'établissement sur le lien (filtre par tenant)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="subject_links")
    subject = models.ForeignKey("core.Subject", on_delete=models.PROTECT, related_name="teacher_links")

    establishment = models.ForeignKey(
        EstablishmentProfile,
        on_delete=models.PROTECT,
        related_name="teacher_subject_links",
        help_text="Copie de l'établissement pour ce lien (optimisation de filtres).",
    )

    class Meta:
        db_table = "core_teacher_subject"
        constraints = [
            models.UniqueConstraint(fields=["teacher", "subject"], name="uq_teacher_subject_once")
        ]
        indexes = [
            models.Index(fields=["establishment", "subject"], name="idx_tsubj_estab_subject"),
            models.Index(fields=["teacher"], name="idx_tsubj_teacher"),
        ]

    def clean(self):
        # 1) Le lien doit porter le même établissement que le professeur
        if self.teacher.establishment_id != self.establishment_id:
            raise ValidationError({"establishment": "Doit égaler l'établissement du professeur."})

        # 2) (Optionnel) Si Subject est scopé établissement, vérifier aussi subject.establishment_id
        subj_estab_id = getattr(self.subject, "establishment_id", None)
        if subj_estab_id and subj_estab_id != self.establishment_id:
            raise ValidationError({"subject": "La matière doit appartenir au même établissement (tenant)."})

    def save(self, *args, **kwargs):
        # Auto-renseigner l'établissement si absent
        if not self.establishment_id and self.teacher_id:
            self.establishment_id = self.teacher.establishment_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher.user.full_name} → {getattr(self.subject, 'name', self.subject_id)}"


class TeacherLevel(models.Model):
    """
    Liaison Professeur ↔ Niveau.
    - Unicité (teacher, level)
    - Contrôle d'établissement identique
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="level_links")
    level = models.ForeignKey("core.Level", on_delete=models.PROTECT, related_name="teacher_links")

    establishment = models.ForeignKey(
        EstablishmentProfile,
        on_delete=models.PROTECT,
        related_name="teacher_level_links",
        help_text="Copie de l'établissement pour ce lien (optimisation de filtres).",
    )

    class Meta:
        db_table = "core_teacher_level"
        constraints = [
            models.UniqueConstraint(fields=["teacher", "level"], name="uq_teacher_level_once")
        ]
        indexes = [
            models.Index(fields=["establishment", "level"], name="idx_tlvl_estab_level"),
            models.Index(fields=["teacher"], name="idx_tlvl_teacher"),
        ]

    def clean(self):
        if self.teacher.establishment_id != self.establishment_id:
            raise ValidationError({"establishment": "Doit égaler l'établissement du professeur."})
        lvl_estab_id = getattr(self.level, "establishment_id", None)
        if lvl_estab_id and lvl_estab_id != self.establishment_id:
            raise ValidationError({"level": "Le niveau doit appartenir au même établissement (tenant)."})

    def save(self, *args, **kwargs):
        if not self.establishment_id and self.teacher_id:
            self.establishment_id = self.teacher.establishment_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher.user.full_name} → {getattr(self.level, 'name', self.level_id)}"
