"""
Modèle Department (Département) + DepartmentMember (chef/RA/prof)
-----------------------------------------------------------------
Objectifs
- Représenter un département par tenant (FK -> EstablishmentProfile).
- Gérer le chef de département (unique), les RA (plusieurs) et les professeurs rattachés.
- Assurer la cohérence multi-tenant sur toutes les liaisons.
- Exposer des index et contraintes adaptés aux listes massives (10k+).

Données prises en compte
- Department :
  - establishment : tenant (obligatoire, FK PROTECT)
  - code          : code court unique par établissement (ex: "INFO", "PHY")
  - name          : nom affiché
  - head          : chef de département (User) – doit appartenir au même établissement
  - description   : texte optionnel
  - timestamps    : created_at, updated_at
- DepartmentMember :
  - department    : département cible
  - establishment : copie du tenant pour filtres rapides
  - user          : membre (User) – doit appartenir au même établissement
  - role          : "HEAD" | "RA" | "TEACHER"
  - unicité       : (department, user, role) unique
  - contrainte    : 1 seul "HEAD" par department (enforcé en clean())
"""

from __future__ import annotations

import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models.establishment import Establishment
from core.models.user import User


class Department(models.Model):
    """
    Département d'un établissement (tenant).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="departments",
        help_text="Établissement (tenant) propriétaire du département.",
    )

    code = models.CharField(
        max_length=24,
        help_text="Code court unique par établissement (ex: 'INFO').",
    )
    name = models.CharField(max_length=255, help_text="Nom complet du département.")
    description = models.TextField(blank=True)

    # Chef de département (unique) – doit appartenir au même établissement
    head = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="headed_departments",
        null=True,
        blank=True,
        help_text="Chef de département (User) ; doit appartenir au même établissement.",
    )

    # Accès pratique aux profs via M2M 'through' (DepartmentMember)
    teachers = models.ManyToManyField(
        User,
        through="DepartmentMember",
        related_name="departments",
        blank=True,
        help_text="Professeurs/RA/chef rattachés via DepartmentMember.",
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="Créé le (auto).")
    updated_at = models.DateTimeField(auto_now=True, help_text="MAJ le (auto).")

    class Meta:
        db_table = "core_department"
        verbose_name = "Département"
        verbose_name_plural = "Départements"
        constraints = [
            # Code unique par établissement
            models.UniqueConstraint(
                fields=["establishment", "code"],
                name="uq_department_code_per_establishment",
            ),
        ]
        indexes = [
            models.Index(fields=["establishment", "code"], name="idx_dept_estab_code"),
            models.Index(fields=["establishment", "name"], name="idx_dept_estab_name"),
        ]
        ordering = ["establishment_id", "code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def clean(self):
        """
        Intégrité multi-tenant :
        - head, si renseigné, doit appartenir au même établissement
          (User.establishment == self.establishment pour un head non-établissement)
        """
        if self.head:
            # Un compte 'établissement' n'est pas un chef valide
            if self.head.role == "establishment":
                raise ValidationError({"head": "Le chef doit être un user du tenant, pas un compte établissement."})

            if self.head.establishment_id != self.establishment_id:
                raise ValidationError({"head": "Le chef doit appartenir au même établissement (tenant)."})


class DepartmentMemberRole(models.TextChoices):
    """
    Rôles internes au département (contexte départemental).
    """
    HEAD = "HEAD", "Chef de département"
    RA = "RA", "Responsable adjoint"
    TEACHER = "TEACHER", "Professeur"


class DepartmentMember(models.Model):
    """
    Liaison User ↔ Department avec rôle contextualisé (HEAD/RA/TEACHER).

    Contraintes :
    - (department, user, role) unique → pas de doublon.
    - Tous les objets (department, establishment, user) doivent partager le même tenant.
    - Un seul HEAD par department (enforcé en clean()).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text="Département visé par l'adhésion.",
    )
    # Copie pour filtres performants par tenant
    establishment = models.ForeignKey(
        Establishment,
        on_delete=models.PROTECT,
        related_name="department_members",
        help_text="Établissement (tenant) – doit correspondre à department.establishment.",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="department_memberships",
        help_text="Utilisateur membre du département (prof/RA/chef).",
    )

    role = models.CharField(max_length=12, choices=DepartmentMemberRole.choices)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_department_member"
        verbose_name = "Membre de département"
        verbose_name_plural = "Membres de département"
        constraints = [
            # Pas de doublon exact
            models.UniqueConstraint(
                fields=["department", "user", "role"],
                name="uq_dept_user_role_once",
            ),
            # ⚠️ Un SEUL département par professeur (dans un établissement)
            models.UniqueConstraint(
                fields=["establishment", "user"],
                condition=Q(role=DepartmentMemberRole.TEACHER),
                name="uq_one_department_per_teacher_per_establishment",
            ),
        ]
        indexes = [
            models.Index(fields=["establishment", "department"], name="idx_dmem_estab_dept"),
            models.Index(fields=["department", "role"], name="idx_dmem_dept_role"),
            models.Index(fields=["user"], name="idx_dmem_user"),
        ]
        ordering = ["department_id", "role", "-created_at"]

    def __str__(self) -> str:
        return f"{self.department.code} — {self.user.full_name} [{self.role}]"

    def clean(self):
        """
        Intégrité & sécurité (multi-tenant + règles métier) :
        - establishment == department.establishment
        - user.establishment == establishment
        - HEAD : un seul par department
        - Rôles autorisés selon user.role (ex.: TEACHER → user.role == 'teacher')
        """
        # Cohérence tenant
        if self.establishment_id != self.department.establishment_id:
            raise ValidationError({"establishment": "Doit égaler l'établissement du département."})
        if self.user.role != "establishment" and self.user.establishment_id != self.establishment_id:
            raise ValidationError({"user": "L'utilisateur doit appartenir au même établissement (tenant)."})

        # Un seul chef par département
        if self.role == DepartmentMemberRole.HEAD:
            exists = (
                DepartmentMember.objects
                .filter(department_id=self.department_id, role=DepartmentMemberRole.HEAD)
                .exclude(pk=self.pk)
                .exists()
            )
            if exists:
                raise ValidationError({"role": "Un seul chef de département est autorisé."})

        # Cohérence de rôle (souple mais sécurisant)
        if self.role == DepartmentMemberRole.TEACHER and self.user.role != "teacher":
            raise ValidationError({"user": "Seuls les utilisateurs 'teacher' peuvent être TEACHER du département."})
        # RA et HEAD : souvent des enseignants seniors ou admin ; on autorise teacher/admin
        if self.role in (DepartmentMemberRole.RA, DepartmentMemberRole.HEAD) and self.user.role not in ("teacher", "admin"):
            raise ValidationError({"user": "RA/HEAD doivent être 'teacher' ou 'admin'."})

    def save(self, *args, **kwargs):
        # Auto-renseigner l'établissement si absent
        if not self.establishment_id:
            self.establishment_id = self.department.establishment_id
        self.full_clean()
        return super().save(*args, **kwargs)
