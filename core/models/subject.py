# core/models/subject.py
"""
Modèle Subject (Matière) + ProgramSubject (liaison filière↔matière)
==================================================================
Objectifs (exigences respectées)
- Multi-tenant strict : chaque matière appartient à **un établissement** (tenant).
- Hiérarchie claire : la matière est rattachée à **un département** ; l’ouverture
  de la matière dans une **filière (Program)** se fait via un pivot ProgramSubject.
- Performance : index ciblés (tenant+code/department), unicité du code par tenant,
  validations cohérentes inter-tenant, `save().full_clean()` systématique.
- Sécurité & SOLID : validations dans `clean()`, responsabilité unique par modèle,
  zéro duplication (les liens Program → Department/Level sont déjà garantis par Program).
- Compatibilité : côté professeurs, l’assignation aux matières passe par le pivot
  existant `TeacherSubject` (pas redéfini ici).

Champs pris en compte
---------------------
Subject :
- establishment     : FK(Establishment) — tenant propriétaire
- department        : FK(Department)    — rattachement académique
- code              : code court **unique par établissement** (ex: "ALG101")
- name              : libellé de la matière
- coefficient       : pondération (optionnelle)
- ects              : crédits (optionnels)
- hours_total       : volume horaire (optionnel)
- is_active         : statut d’activation pédagogique
- description       : descriptif (optionnel)
- created_at / updated_at

ProgramSubject (pivot) :
- establishment     : FK(Establishment) — copie du tenant pour filtres massifs
- program           : FK(Program)       — filière où la matière est ouverte
- subject           : FK(Subject)
- semester          : semestre (1..2 ou 1..6 selon maquette — ici 1..2 par défaut)
- is_mandatory      : obligatoire ?
- coefficient       : surclassement local optionnel
- hours            : volume horaire local optionnel
- unicité (program, subject)
"""

from __future__ import annotations

import uuid
from django.core.exceptions import ValidationError
from django.db import models

from core.models.establishment import Establishment
from core.models.department import Department
from core.models.program import Program


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="subjects",
        help_text="Établissement (tenant) propriétaire de la matière.",
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="subjects",
        help_text="Département académique porteur de la matière.",
    )

    code = models.CharField(
        max_length=32,
        help_text="Code unique par établissement (ex: 'ALG101').",
    )
    name = models.CharField(max_length=255, help_text="Nom de la matière (ex: Algèbre 1).")

    coefficient = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Pondération globale (optionnel)."
    )
    ects = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Crédits ECTS (optionnel)."
    )
    hours_total = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Volume horaire total (optionnel, en heures)."
    )

    is_active = models.BooleanField(default=True, help_text="Matière active/inactive.")
    description = models.TextField(blank=True)

    # Ouvertures de la matière dans des filières (M2M via pivot ProgramSubject)
    programs = models.ManyToManyField(
        Program, through="ProgramSubject", related_name="subjects", blank=True,
        help_text="Filières dans lesquelles la matière est ouverte (via pivot)."
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_subject"
        verbose_name = "Matière"
        verbose_name_plural = "Matières"
        constraints = [
            models.UniqueConstraint(
                fields=["establishment", "code"],
                name="uq_subject_code_per_establishment",
            ),
        ]
        indexes = [
            models.Index(fields=["establishment", "code"], name="idx_subject_estab_code"),
            models.Index(fields=["establishment", "department"], name="idx_subject_estab_dept"),
            models.Index(fields=["establishment", "is_active"], name="idx_subject_estab_active"),
        ]
        ordering = ["establishment_id", "department_id", "code"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} — {self.name}"

    # ---------- Intégrité multi-tenant ----------
    def clean(self):
        # Cohérence tenant : department.establishment == establishment
        if self.department and self.department.establishment_id != self.establishment_id:
            raise ValidationError({"department": "Doit appartenir au même établissement (tenant)."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProgramSubject(models.Model):
    """
    Ouvre une matière (Subject) dans une filière (Program) du même tenant.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="program_subject_links",
        help_text="Copie du tenant pour filtres massifs.",
    )

    program = models.ForeignKey(
        Program, on_delete=models.PROTECT, related_name="program_subject_links",
        help_text="Filière (Program) concernée."
    )

    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, related_name="program_subject_links",
        help_text="Matière ouverte dans la filière."
    )

    # Paramètres pédagogiques locaux à la filière
    semester = models.PositiveSmallIntegerField(
        default=1, help_text="Semestre (1 ou 2)."
    )
    is_mandatory = models.BooleanField(default=True, help_text="Matière obligatoire dans cette filière ?")
    
    coefficient = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Coefficient spécifique à la filière (écrase la valeur globale si défini)."
    )
    hours = models.PositiveIntegerField(
        null=True, blank=True, help_text="Volume horaire spécifique (optionnel)."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_program_subject"
        verbose_name = "Ouverture de matière (filière)"
        verbose_name_plural = "Ouvertures de matière (filières)"
        constraints = [
            models.UniqueConstraint(
                fields=["program", "subject"],
                name="uq_program_subject_once",
            ),
        ]
        indexes = [
            models.Index(fields=["establishment", "program"], name="idx_ps_estab_program"),
            models.Index(fields=["establishment", "subject"], name="idx_ps_estab_subject"),
            models.Index(fields=["program", "semester"], name="idx_ps_program_semester"),
        ]
        ordering = ["program_id", "semester", "subject_id"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{getattr(self.program, 'code', self.program_id)} ↔ {getattr(self.subject, 'code', self.subject_id)} (S{self.semester})"

    # ---------- Intégrité & sécurité ----------
    def clean(self):
        # 1) Cohérence tenant : program.establishment == subject.establishment == establishment
        if self.program and self.subject:
            if self.program.establishment_id != self.subject.establishment_id:
                raise ValidationError({"program": "Program et Subject doivent appartenir au même établissement."})
            if self.establishment_id and self.program.establishment_id != self.establishment_id:
                raise ValidationError({"establishment": "Doit égaler le tenant de program/subject."})

        # 2) Semestre simple (1..2) — adapte si tu gères plus de semestres
        if self.semester < 1 or self.semester > 2:
            raise ValidationError({"semester": "Le semestre doit être 1 ou 2."})

    def save(self, *args, **kwargs):
        if not self.establishment_id and self.program_id:
            self.establishment_id = self.program.establishment_id
        self.full_clean()
        return super().save(*args, **kwargs)
