# core/models/attendance.py
"""
Modèle Attendance (présences aux évaluations)
=============================================
Objectifs (exigences respectées)
- Enregistrer la **présence** d’un étudiant à une **évaluation** (Exam).
- Multi-tenant strict : présence rattachée à un **établissement** ; toutes les FK
  (evaluation, student, marked_by) doivent pointer dans le **même tenant**.
- Unicité : **une ligne par (evaluation, student)**.
- Performance : index par tenant + évaluation + statut, validations cohérentes,
  `save().full_clean()` systématique.
- Sécurité : seules les personnes du tenant (prof/admin) peuvent marquer une présence.

Champs pris en compte
---------------------
- establishment  : FK(Establishment) — tenant
- evaluation     : FK(Exam)          — évaluation concernée (doit porter establishment)
- student        : FK(StudentProfile) — étudiant concerné
- status         : PRESENT | ABSENT | LATE | EXCUSED
- source         : MANUAL | IMPORT | PROCTORING | API
- marked_by      : FK(User) (optionnel) — qui a marqué (enseignant/admin)
- marked_at      : DateTime (auto)
- note           : commentaire (optionnel)

Contraintes/Index
-----------------
- unique (evaluation, student)
- indexes : (establishment, evaluation), (evaluation, status), (establishment, status)
"""

from __future__ import annotations

import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models.establishment import Establishment
from core.models.user import User
from core.models.student import StudentProfile

# ⚠️ Le modèle d'évaluation doit exister (dans core/models/exam.py).
#    On suppose la classe nommée "Exam" et qu'elle porte un FK establishment.
#    Si ton modèle s'appelle autrement (ex: Evaluation), ajuste la string ci-dessous.
EVALUATION_MODEL = "core.Exam"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Présent"
    ABSENT = "absent", "Absent"
    LATE = "late", "Retard"
    EXCUSED = "excused", "Excusé"


class AttendanceSource(models.TextChoices):
    MANUAL = "manual", "Saisie manuelle"
    IMPORT = "import", "Import"
    PROCTORING = "proctoring", "Proctoring"
    API = "api", "API"


class Attendance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="attendances",
        help_text="Établissement (tenant) porteur de la présence.",
    )

    evaluation = models.ForeignKey(
        EVALUATION_MODEL,
        on_delete=models.PROTECT,
        related_name="attendances",
        help_text="Évaluation (Exam) concernée.",
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.PROTECT,
        related_name="attendances",
        help_text="Étudiant évalué.",
    )

    status = models.CharField(max_length=10, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    source = models.CharField(max_length=12, choices=AttendanceSource.choices, default=AttendanceSource.MANUAL)

    marked_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="marked_attendances",
        help_text="Utilisateur qui a saisi la présence (prof/admin)."
    )
    marked_at = models.DateTimeField(default=timezone.now, help_text="Horodatage de la saisie.")

    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "core_attendance"
        verbose_name = "Présence"
        verbose_name_plural = "Présences"
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "student"],
                name="uq_attendance_eval_student_once",
            ),
        ]
        indexes = [
            models.Index(fields=["establishment", "evaluation"], name="idx_att_estab_eval"),
            models.Index(fields=["evaluation", "status"], name="idx_att_eval_status"),
            models.Index(fields=["establishment", "status"], name="idx_att_estab_status"),
        ]
        ordering = ["evaluation_id", "student_id"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{getattr(self.evaluation, 'id', self.evaluation_id)} — {getattr(self.student.user, 'full_name', self.student_id)} [{self.status}]"

    # ---------- Intégrité & sécurité ----------
    def clean(self):
        """
        - Toutes les FK doivent partager le **même tenant**.
        - Le marqueur (marked_by), s'il est présent, doit appartenir au tenant (sauf superuser).
        """
        # 1) Cohérence tenant évaluation/étudiant/establishment
        eval_estab_id = getattr(self.evaluation, "establishment_id", None)
        if eval_estab_id and eval_estab_id != self.establishment_id:
            raise ValidationError({"evaluation": "L'évaluation doit appartenir au même établissement (tenant)."})

        if self.student.establishment_id != self.establishment_id:
            raise ValidationError({"student": "L'étudiant doit appartenir au même établissement (tenant)."})

        # 2) marked_by dans le tenant (sauf superuser)
        if self.marked_by and not self.marked_by.is_superuser:
            if self.marked_by.establishment_id != self.establishment_id:
                raise ValidationError({"marked_by": "Le marqueur doit appartenir au même établissement (tenant)."})

        # 3) Statut cohérent
        if self.status not in AttendanceStatus.values:
            raise ValidationError({"status": "Statut de présence invalide."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
