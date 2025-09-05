# core/models/question.py
"""
Questions d'évaluation, options QCM et temps passé par question (par étudiant)
=============================================================================

Matérialise :
- Question : QCM ou RÉPONSE LIBRE, ordonnancement, points, temps attendu (optionnel).
- QuestionOption : options d'un QCM (0..N correctes). Plusieurs réponses correctes possibles.
- QuestionTiming : temps passé **par étudiant** et **par question** pour une évaluation.

Exigences respectées :
- Les questions appartiennent à une **Exam** (tenant hérité via FK) et à un **Subject**.
- Points par question, type, énoncé, description/explication optionnelle.
- Mesure du **temps passé par question** (QuestionTiming.time_spent_seconds).
- Perfs : index par tenant/exam/order ; unicité `(exam, order)` ; options indexées.
- Sécurité : validations inter-tenant sur toutes les FK.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models

from core.models.establishment import Establishment
from core.models.subject import Subject
from core.models.exam import Exam
from core.models.student import StudentProfile


class QuestionType(models.TextChoices):
    MCQ = "mcq", "QCM (choix multiples)"
    OPEN = "open", "Réponse libre"


class Question(models.Model):
    """
    Question rattachée à une Exam.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment, on_delete=models.PROTECT, related_name="questions",
        help_text="Établissement (tenant) porteur de la question."
    )

    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="questions",
        help_text="Évaluation parente."
    )

    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, related_name="questions",
        help_text="Matière concernée (doit correspondre à exam.subject)."
    )

    qtype = models.CharField(max_length=10, choices=QuestionType.choices, default=QuestionType.MCQ)

    # Contenu & barème
    prompt = models.TextField(help_text="Énoncé de la question.")
    points = models.DecimalField(
        max_digits=7, decimal_places=2, default=Decimal("1.00"),
        help_text="Points attribués à la question."
    )

    # Ordonancement dans l'exam
    order = models.PositiveIntegerField(
        default=1,
        help_text="Ordre d'affichage/traitement dans l'évaluation (1..N)."
    )

    # Temps attendu (optionnel) — mesure réelle stockée côté QuestionTiming
    expected_time_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Temps indicatif attendu pour répondre (en secondes)."
    )

    explanation = models.TextField(
        blank=True,
        help_text="Explication/correction (optionnel, pour diffusion après l'exam)."
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_question"
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        constraints = [
            # Interdit deux questions avec le même ordre dans la même Exam
            models.UniqueConstraint(fields=["exam", "order"], name="uq_question_exam_order"),
        ]
        indexes = [
            models.Index(fields=["establishment", "exam"], name="idx_q_estab_exam"),
            models.Index(fields=["exam", "order"], name="idx_q_exam_order"),
            models.Index(fields=["establishment", "qtype"], name="idx_q_estab_qtype"),
        ]
        ordering = ["exam_id", "order", "id"]

    def __str__(self):  # pragma: no cover
        return f"Q{self.order} [{self.qtype}] — {self.points} pts"

    def clean(self):
        # Cohérence tenant : exam.establishment == establishment
        if self.exam.establishment_id != self.establishment_id:
            raise ValidationError({"exam": "L'examen doit appartenir au même établissement (tenant)."})
        # La matière de la question doit correspondre à celle de l'exam
        if self.subject_id != self.exam.subject_id:
            raise ValidationError({"subject": "Doit correspondre à la matière de l'examen."})
        # Points > 0
        if self.points <= 0:
            raise ValidationError({"points": "Les points doivent être > 0."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class QuestionOption(models.Model):
    """
    Option d'un QCM (0..N correctes). Plusieurs bonnes réponses possibles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options",
        help_text="Question parente."
    )

    label = models.TextField(help_text="Texte de l'option.")
    is_correct = models.BooleanField(default=False, help_text="Cette option est-elle correcte ?")
    order = models.PositiveIntegerField(default=1, help_text="Ordre d'affichage de l'option.")

    class Meta:
        db_table = "core_question_option"
        verbose_name = "Option de question"
        verbose_name_plural = "Options de question"
        constraints = [
            models.UniqueConstraint(fields=["question", "order"], name="uq_qopt_question_order"),
        ]
        indexes = [
            models.Index(fields=["question"], name="idx_qopt_question"),
            models.Index(fields=["question", "is_correct"], name="idx_qopt_correct"),
        ]
        ordering = ["question_id", "order", "id"]

    def __str__(self):  # pragma: no cover
        return f"Option {self.order} ({'✔' if self.is_correct else '✘'})"


class QuestionTiming(models.Model):
    """
    Temps passé par un étudiant sur une question donnée pendant une évaluation.
    - Conçu pour stocker un cumul par (exam, question, student). L'application/worker
      met à jour `time_spent_seconds` en incrémentant (idempotence au niveau service).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment, on_delete=models.PROTECT, related_name="question_timings",
        help_text="Tenant (doit égaler celui de l'examen/étudiant)."
    )
    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="question_timings",
        help_text="Examen concerné."
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="timings",
        help_text="Question concernée."
    )
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="question_timings",
        help_text="Étudiant concerné."
    )

    time_spent_seconds = models.PositiveIntegerField(default=0, help_text="Temps total passé (secondes).")

    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_question_timing"
        verbose_name = "Temps par question"
        verbose_name_plural = "Temps par question"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "question", "student"],
                name="uq_qt_exam_question_student",
            ),
        ]
        indexes = [
            models.Index(fields=["establishment", "exam"], name="idx_qt_estab_exam"),
            models.Index(fields=["exam", "question"], name="idx_qt_exam_question"),
            models.Index(fields=["student"], name="idx_qt_student"),
        ]
        ordering = ["exam_id", "question_id", "student_id"]

    def clean(self):
        # Cohérence tenant partout
        if self.exam.establishment_id != self.establishment_id:
            raise ValidationError({"exam": "Examen d'un autre établissement."})
        if self.student.establishment_id != self.establishment_id:
            raise ValidationError({"student": "Étudiant d'un autre établissement."})
        if self.question.exam_id != self.exam_id:
            raise ValidationError({"question": "La question ne fait pas partie de cet examen."})

    def save(self, *args, **kwargs):
        if not self.establishment_id and self.exam_id:
            self.establishment_id = self.exam.establishment_id
        self.full_clean()
        return super().save(*args, **kwargs)
