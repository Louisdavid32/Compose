# core/models/exam.py
"""
Modèles d'évaluation (Exam) — multi-tenant, performants, prêts prod
===================================================================

Ce module matérialise :
- Exam (évaluation) : fenêtre temporelle, type, barème (10/20/100), statut, sécurité,
  cache de points, moyenne, liens tenant/subject/program, auteur, annulation.
- ExamProgram (audience optionnelle) : pivot pour cibler **plusieurs filières** (programmes)
  avec une même évaluation (ex : inter-filières).
  
Règles clés respectées (exigences) :
- Multi-tenant strict : toutes les FK doivent appartenir au **même établissement (tenant)**.
- Planification : seuls **teacher**, **RA**, **HEAD** (du département de la matière) et **admin**
  peuvent créer/planifier/annuler une évaluation (contrôle en `clean()`).
- Fenêtre & durée : `starts_at < ends_at`. `time_limit_seconds` (limite globale) optionnelle.
- Barème : `grading_scale ∈ {10, 20, 100}`.
- Moyenne : `average_score` stockée (mise à jour par service/asynchrone).
- Perfs : index `(establishment, subject, status, starts_at)`, cache `total_points_cache`.
- Sécurité : `access_code` (optionnel), drapeaux `shuffle_questions`, `shuffle_options`,
  `proctoring_required`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models.establishment import Establishment
from core.models.user import User
from core.models.subject import Subject
from core.models.program import Program
from core.models.department import DepartmentMember, DepartmentMemberRole


class ExamType(models.TextChoices):
    EXAM = "exam", "Examen"
    QUIZ = "quiz", "Quiz"
    ASSIGNMENT = "assignment", "Devoir"
    PRACTICAL = "practical", "TP"
    ORAL = "oral", "Oral"


class ExamStatus(models.TextChoices):
    DRAFT = "draft", "Brouillon"
    SCHEDULED = "scheduled", "Planifiée"
    ONGOING = "ongoing", "En cours"
    ENDED = "ended", "Terminée"
    CANCELLED = "cancelled", "Annulée"
    ARCHIVED = "archived", "Archivée"


class Exam(models.Model):
    """
    Évaluation planifiée pour une matière (subject), optionnellement ciblée vers N filières.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Scoping tenant
    establishment = models.ForeignKey(
        Establishment, on_delete=models.PROTECT, related_name="exams",
        help_text="Établissement (tenant) porteur de l'évaluation."
    )

    # Matière obligatoire (détermine le département)
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, related_name="exams",
        help_text="Matière concernée par l'évaluation (doit être du même établissement)."
    )

    # Titre & typologie
    title = models.CharField(max_length=255, help_text="Titre de l'évaluation.")
    exam_type = models.CharField(max_length=20, choices=ExamType.choices, default=ExamType.EXAM)

    # Fenêtre temporelle & limite globale (optionnelle)
    starts_at = models.DateTimeField(help_text="Début de la fenêtre de l'évaluation.")
    ends_at = models.DateTimeField(help_text="Fin de la fenêtre de l'évaluation.")
    time_limit_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Durée max autorisée par candidat (en secondes). Optionnel."
    )

    # Barème (sur 10/20/100)
    grading_scale = models.PositiveSmallIntegerField(
        choices=((10, "Sur 10"), (20, "Sur 20"), (100, "Sur 100")), default=20,
        help_text="Barème de l'évaluation."
    )

    description = models.TextField(blank=True)

    # Sécurité & déroulé
    access_code = models.CharField(
        max_length=20, blank=True,
        help_text="Code d'accès (optionnel) pour restreindre l'entrée."
    )
    shuffle_questions = models.BooleanField(default=True, help_text="Mélanger l'ordre des questions.")
    shuffle_options = models.BooleanField(default=True, help_text="Mélanger l'ordre des options (QCM).")
    proctoring_required = models.BooleanField(default=False, help_text="Surveillance requise (proctoring).")

    # Statut & pilotage
    status = models.CharField(max_length=20, choices=ExamStatus.choices, default=ExamStatus.DRAFT)

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="exams_created",
        help_text="Auteur (teacher/admin/RA/HEAD) appartenant au tenant."
    )
    cancelled_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="exams_cancelled",
        help_text="Utilisateur ayant annulé l'évaluation (si status=CANCELLED)."
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="Date de publication (optionnel).")

    # KPIs/cache
    total_points_cache = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="Somme des points des questions (cache)."
    )
    average_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Moyenne des notes (calculée asynchrone)."
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    # Audience optionnelle : lier N filières à la même évaluation
    programs = models.ManyToManyField(
        Program, through="ExamProgram", related_name="exams", blank=True,
        help_text="Filières ciblées par l'évaluation (optionnel ; via pivot ExamProgram)."
    )

    class Meta:
        db_table = "core_exam"
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"
        indexes = [
            models.Index(fields=["establishment", "subject"], name="idx_exam_estab_subject"),
            models.Index(fields=["establishment", "status"], name="idx_exam_estab_status"),
            models.Index(fields=["establishment", "starts_at"], name="idx_exam_estab_start"),
            models.Index(fields=["starts_at", "ends_at"], name="idx_exam_window"),
        ]
        ordering = ["-starts_at", "-created_at"]

    def __str__(self):  # pragma: no cover
        return f"{self.title} — {self.subject.code} ({self.starts_at:%Y-%m-%d %H:%M})"

    # ---------- Propriétés utiles ----------

    @property
    def department(self):
        """Département académique (dérivé de la matière)."""
        return getattr(self.subject, "department", None)

    @property
    def is_active_window(self) -> bool:
        now = timezone.now()
        return self.status in (ExamStatus.SCHEDULED, ExamStatus.ONGOING) and self.starts_at <= now <= self.ends_at

    # ---------- Intégrité & sécurité ----------

    def _validate_scheduler_permissions(self):
        """
        Règles de pilotage :
        - L'auteur/cancelleur doit appartenir au tenant.
        - Autorisés : admin (toujours), teacher du département de la matière,
          RA/HEAD du même département.
        """
        dept = self.department
        # created_by
        if self.created_by and not self.created_by.is_superuser:
            if self.created_by.establishment_id != self.establishment_id:
                raise ValidationError({"created_by": "Doit appartenir au même établissement (tenant)."})
            if self.created_by.is_staff:
                return  # admins/staff autorisés (même tenant)
            # teacher/RA/HEAD du même département
            ok = DepartmentMember.objects.filter(
                establishment_id=self.establishment_id,
                department_id=getattr(dept, "id", None),
                user_id=self.created_by_id,
                role__in=[DepartmentMemberRole.TEACHER, DepartmentMemberRole.RA, DepartmentMemberRole.HEAD],
            ).exists()
            if not ok:
                raise ValidationError({"created_by": "Permissions insuffisantes pour planifier cette évaluation."})

        # cancelled_by
        if self.status == ExamStatus.CANCELLED and self.cancelled_by and not self.cancelled_by.is_superuser:
            if self.cancelled_by.establishment_id != self.establishment_id:
                raise ValidationError({"cancelled_by": "Doit appartenir au même établissement (tenant)."})
            if self.cancelled_by.is_staff:
                return
            ok = DepartmentMember.objects.filter(
                establishment_id=self.establishment_id,
                department_id=getattr(dept, "id", None),
                user_id=self.cancelled_by_id,
                role__in=[DepartmentMemberRole.TEACHER, DepartmentMemberRole.RA, DepartmentMemberRole.HEAD],
            ).exists()
            if not ok:
                raise ValidationError({"cancelled_by": "Permissions insuffisantes pour annuler cette évaluation."})

    def clean(self):
        # Cohérence tenant
        if self.subject.establishment_id != self.establishment_id:
            raise ValidationError({"subject": "La matière doit appartenir au même établissement (tenant)."})

        if self.created_by and (self.created_by.establishment_id != self.establishment_id) and not self.created_by.is_superuser:
            raise ValidationError({"created_by": "Doit appartenir au même établissement (tenant)."})

        if self.cancelled_by and (self.cancelled_by.establishment_id != self.establishment_id) and not self.cancelled_by.is_superuser:
            raise ValidationError({"cancelled_by": "Doit appartenir au même établissement (tenant)."})

        # Fenêtre valide
        if self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": "La fin doit être postérieure au début."})

        # Limite globale optionnelle
        if self.time_limit_seconds is not None and self.time_limit_seconds == 0:
            raise ValidationError({"time_limit_seconds": "La durée doit être > 0 seconde."})

        # Contrôle des permissions de pilotage
        self._validate_scheduler_permissions()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ExamProgram(models.Model):
    """
    Pivot multi-tenant : lie une évaluation à une filière (audience).
    - Permet de cibler **plusieurs Program** pour la même Exam.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="program_links")
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="exam_links")

    establishment = models.ForeignKey(
        Establishment, on_delete=models.PROTECT, related_name="exam_program_links",
        help_text="Copie du tenant pour filtres massifs."
    )

    class Meta:
        db_table = "core_exam_program"
        constraints = [
            models.UniqueConstraint(fields=["exam", "program"], name="uq_exam_program_once")
        ]
        indexes = [
            models.Index(fields=["establishment", "program"], name="idx_exprog_estab_program"),
            models.Index(fields=["exam"], name="idx_exprog_exam"),
        ]
        ordering = ["exam_id", "program_id"]

    def clean(self):
        if self.exam.establishment_id != self.establishment_id:
            raise ValidationError({"establishment": "Doit égaler l'établissement de l'évaluation."})
        if self.program.establishment_id != self.establishment_id:
            raise ValidationError({"program": "La filière doit appartenir au même établissement (tenant)."})

    def save(self, *args, **kwargs):
        if not self.establishment_id and self.exam_id:
            self.establishment_id = self.exam.establishment_id
        self.full_clean()
        return super().save(*args, **kwargs)
