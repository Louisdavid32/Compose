"""
Modèle Program (Filière)
------------------------
Objectifs
- Représenter une filière rattachée à un **département** et à un **niveau** (dans le même tenant).
- Contrainte d'unicité du 'code' par établissement.
- Garantir la cohérence: le niveau doit appartenir au même département/tenant.

Données prises en compte
- establishment : tenant
- department    : département parent
- level         : niveau parent (du même département)
- code          : code unique par établissement (ex: 'GL', 'RESEAU', 'PHY-L3')
- name          : nom de la filière
- coefficient   : optionnel (pondération)
- description   : texte optionnel
"""

from __future__ import annotations

import uuid
from django.core.exceptions import ValidationError
from django.db import models

from core.models.establishment import Establishment
from core.models.department import Department
from core.models.level import Level


class Program(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="programs",
        help_text="Établissement (tenant) propriétaire de la filière.",
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="programs",
        help_text="Département parent.",
    )

    level = models.ForeignKey(
        Level,
        on_delete=models.PROTECT,
        related_name="programs",
        help_text="Niveau parent (doit appartenir au même département/tenant).",
    )

    code = models.CharField(max_length=32, help_text="Code unique par établissement (ex: 'GL').")
    name = models.CharField(max_length=255, help_text="Nom de la filière.")
    coefficient = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Pondération (optionnel)."
    )
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_program"
        verbose_name = "Filière"
        verbose_name_plural = "Filières"
        constraints = [
            models.UniqueConstraint(
                fields=["establishment", "code"],
                name="uq_program_code_per_establishment",
            ),
        ]
        indexes = [
            models.Index(fields=["establishment", "department"], name="idx_prog_estab_dept"),
            models.Index(fields=["establishment", "level"], name="idx_prog_estab_level"),
            models.Index(fields=["establishment", "code"], name="idx_prog_estab_code"),
        ]
        ordering = ["establishment_id", "department_id", "level_id", "code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def clean(self):
        """
        Intégrité multi-tenant + relationnelle :
        - department.establishment == establishment
        - level.establishment == establishment
        - level.department == department (cohérence hiérarchique)
        """
        if self.department and self.department.establishment_id != self.establishment_id:
            raise ValidationError({"department": "Le département doit appartenir au même établissement (tenant)."})
        if self.level and self.level.establishment_id != self.establishment_id:
            raise ValidationError({"level": "Le niveau doit appartenir au même établissement (tenant)."})
        if self.level and self.department and self.level.department_id != self.department_id:
            raise ValidationError({"level": "Le niveau doit appartenir au même département."})
