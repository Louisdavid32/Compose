# core/models/imports.py
"""
Ingestion d'étudiants (Excel/CSV) — Modèles de staging & journalisation
-----------------------------------------------------------------------
Objectif
- Accepter des fichiers hétérogènes (entêtes/colonnes variables selon l'école)
- Mapper dynamiquement -> normaliser -> valider -> COMMIT vers les modèles métier
- Rester strictement multi-tenant (scoping par EstablishmentProfile/tenant_id)
- Être performant (index, tailles JSON, status, hash idempotence) et traçable (logs)

Flux
1) ImportBatch (lot) + ImportFile (fichier brut)
2) ImportMapping (correspondances colonnes -> champs plateforme, transforms)
3) StagingStudentRow (lignes normalisées/validées, avec erreurs par ligne)
4) Commit asynchrone -> création/mise à jour User(student)+StudentProfile
5) ImportCommitLog (compte rendu final)

Sécurité & Conformité
- PII en staging: accès restreint, rétention courte (purge planifiée côté tâches)
- Scoping strict: toutes les données rattachées au même Establishment (tenant)
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from core.models.establishment import Establishment
from core.models.user import User
from core.models.validators import validate_school_year


# -------------------------
# Helpers & constantes
# -------------------------

def import_upload_path(instance: "ImportFile", filename: str) -> str:
    """
    Partitionne le stockage par tenant + batch: facilite l'offloading S3/GCS
    et la purge ciblée (GDPR).
    """
    # On sécurise même si batch/establishment n'est pas encore en DB
    est = instance.batch.establishment
    return f"tenants/{est.tenant_id}/imports/{instance.batch_id}/{filename}"


class ImportStatus(models.TextChoices):
    UPLOADED = "uploaded", "Fichier téléversé"
    MAPPED = "mapped", "Mapping sélectionné"
    NORMALIZED = "normalized", "Lignes normalisées"
    VALIDATED = "validated", "Validation terminée"
    READY = "ready_to_commit", "Prêt à intégrer"
    COMMITTED = "committed", "Intégré"
    FAILED = "failed", "Échec"


class SourceType(models.TextChoices):
    CSV = "csv", "CSV"
    XLSX = "xlsx", "Excel (.xlsx)"


class RowStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    NORMALIZED = "normalized", "Normalisée"
    VALID = "valid", "Valide"
    ERROR = "error", "Erreur"


class DedupStrategy(models.TextChoices):
    """
    Stratégie de dédoublonnage à l'intégration:
    - email_phone_matricule: priorité email > phone > matricule
    - email_only / phone_only / matricule_only: au besoin
    """
    EMAIL_PHONE_MATRICULE = "email_phone_matricule", "email > phone > matricule"
    EMAIL_ONLY = "email_only", "email uniquement"
    PHONE_ONLY = "phone_only", "téléphone uniquement"
    MATRICULE_ONLY = "matricule_only", "matricule uniquement"


# -------------------------
# Modèle: ImportMapping
# -------------------------

class ImportMapping(models.Model):
    """
    Gabarit de correspondance des colonnes -> champs cibles plateforme, par établissement.

    field_mappings (JSON) : { "Nom Élève": "full_name", "Mail": "email", ... }
    transforms (JSON)     : [{ "target": "full_name", "ops": ["strip", "title"] }, ...]
    aliases (JSON)        : { "email": ["mail", "e-mail", "adresse mail"], ... }
    required_targets      : ["full_name", ["email","phone","matricule"]]  # au moins un dans le groupe
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment, on_delete=models.CASCADE, related_name="import_mappings"
    )
    name = models.CharField(max_length=100)
    version = models.PositiveIntegerField(default=1)

    field_mappings = models.JSONField(default=dict, help_text="Colonnes source -> champs cibles.")
    transforms = models.JSONField(default=list, help_text="Transformations déclaratives (liste d'étapes).")
    aliases = models.JSONField(default=dict, help_text="Alias d'en-têtes pour auto-détection.")
    required_targets = models.JSONField(
        default=list,
        help_text="Cibles obligatoires (listes/groupe OR). Ex: ['full_name', ['email','phone','matricule']].",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_import_mapping"
        verbose_name = "Mapping d'import"
        verbose_name_plural = "Mappings d'import"
        unique_together = (("establishment", "name", "version"),)
        indexes = [
            models.Index(fields=["establishment", "name"], name="idx_imap_estab_name"),
        ]
        ordering = ["establishment_id", "name", "-version"]

    def __str__(self) -> str:
        return f"{self.establishment.slug}::{self.name}@v{self.version}"

    def clean(self):
        # Taille raisonnable pour éviter les mappings monstrueux
        if len(self.field_mappings) > 200:
            raise ValidationError({"field_mappings": "Mapping trop volumineux (>200 colonnes)."})
        if len(self.transforms) > 500:
            raise ValidationError({"transforms": "Trop d'opérations de transformation."})


# -------------------------
# Modèles: ImportBatch & ImportFile
# -------------------------

class ImportBatch(models.Model):
    """
    Lot d'import pour un établissement et une année scolaire donnée.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    establishment = models.ForeignKey(
        Establishment, on_delete=models.PROTECT, related_name="import_batches"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_import_batches"
    )

    source_type = models.CharField(max_length=10, choices=SourceType.choices)
    original_filename = models.CharField(max_length=255)

    # Année scolaire du lot (par ex. un fichier d'inscriptions de 2025-2026)
    school_year = models.CharField(max_length=9, help_text='Format "YYYY-YYYY".')

    status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.UPLOADED)
    mapping = models.ForeignKey(
        ImportMapping, on_delete=models.SET_NULL, null=True, blank=True, related_name="batches"
    )

    dedup_strategy = models.CharField(
        max_length=32, choices=DedupStrategy.choices, default=DedupStrategy.EMAIL_PHONE_MATRICULE
    )

    # Stats
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)

    # Timeline
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "core_import_batch"
        verbose_name = "Lot d'import"
        verbose_name_plural = "Lots d'import"
        indexes = [
            models.Index(fields=["establishment", "status"], name="idx_ibatch_estab_status"),
            models.Index(fields=["establishment", "school_year"], name="idx_ibatch_estab_year"),
            models.Index(fields=["started_at"], name="idx_ibatch_started"),
        ]
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Batch {self.id} — {self.establishment.slug} — {self.school_year} — {self.status}"

    def clean(self):
        validate_school_year(self.school_year)
        # Mapping, si fourni, doit appartenir au même établissement
        if self.mapping and self.mapping.establishment_id != self.establishment_id:
            raise ValidationError({"mapping": "Le mapping doit appartenir au même établissement."})

    @property
    def tenant_id(self):
        return self.establishment.tenant_id


class ImportFile(models.Model):
    """
    Fichier brut attaché à un lot (CSV/XLSX).
    - On stocke des méta (checksum, headers, rows_count, sheet, encoding), utiles pour l'analyse et le debug.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="files")

    file = models.FileField(
        upload_to=import_upload_path,
        validators=[FileExtensionValidator(["csv", "xlsx"])],
        help_text="Fichier source (CSV/XLSX).",
    )

    checksum_sha256 = models.CharField(max_length=64, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    encoding = models.CharField(max_length=40, blank=True)
    delimiter = models.CharField(max_length=5, blank=True)         # pour CSV
    sheet_name = models.CharField(max_length=255, blank=True)      # pour Excel
    rows_count = models.PositiveIntegerField(default=0)
    headers = models.JSONField(default=list, help_text="Liste des entêtes détectées.")

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_import_file"
        verbose_name = "Fichier d'import"
        verbose_name_plural = "Fichiers d'import"
        indexes = [
            models.Index(fields=["batch"], name="idx_ifile_batch"),
        ]
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.file.name

    def save(self, *args, **kwargs):
        # Calcul du checksum si vide (utile pour dédupliquer côté stockage)
        if self.file and not self.checksum_sha256:
            h = hashlib.sha256()
            for chunk in self.file.chunks():
                h.update(chunk)
            self.checksum_sha256 = h.hexdigest()
            # Rewind pour éviter de perdre le file pointer
            self.file.seek(0)
        return super().save(*args, **kwargs)


# -------------------------
# Modèle: StagingStudentRow
# -------------------------

class StagingStudentRow(models.Model):
    """
    Représente une ligne 'étudiant' en staging pour un batch.
    - raw: dict brut { header_source: value }
    - normalized: dict normalisé { field_target: value } (après mapping + transforms)
    - status: suivi du pipeline de normalisation/validation
    - errors: liste de messages/objets d'erreurs de validation
    - row_hash: hash de la ligne normalisée (idempotence anti-doublon à l'intégration)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_index = models.PositiveIntegerField(help_text="Index de la ligne dans la source (1-based).")

    raw = models.JSONField(default=dict)
    normalized = models.JSONField(default=dict)

    status = models.CharField(max_length=20, choices=RowStatus.choices, default=RowStatus.PENDING)
    errors = models.JSONField(default=list)

    row_hash = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_staging_student_row"
        verbose_name = "Ligne staging étudiant"
        verbose_name_plural = "Lignes staging étudiants"
        unique_together = (("batch", "row_index"),)  # une ligne par index dans le batch
        indexes = [
            models.Index(fields=["batch", "status"], name="idx_srow_batch_status"),
            models.Index(fields=["batch", "row_hash"], name="idx_srow_batch_hash"),
        ]
        ordering = ["batch_id", "row_index"]

    def __str__(self) -> str:
        return f"Row {self.row_index} / Batch {self.batch_id}"

    def set_row_hash(self) -> None:
        """
        Hash stable de la version normalisée pour idempotence (sha256 triée).
        """
        import json
        payload = json.dumps(self.normalized or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.row_hash = hashlib.sha256(payload).hexdigest()

    def clean(self):
        # Vérifs légères côté modèle (les validations métier détaillées sont faites dans le service d'import)
        if self.row_index == 0:
            raise ValidationError({"row_index": "row_index commence à 1."})
        # Normalized peut contenir 'current_school_year' -> on peut vérifier ici si présent
        year = (self.normalized or {}).get("current_school_year")
        if year:
            validate_school_year(year)

    def save(self, *args, **kwargs):
        if self.normalized and not self.row_hash:
            self.set_row_hash()
        return super().save(*args, **kwargs)


# -------------------------
# Modèle: ImportCommitLog
# -------------------------

class ImportCommitLog(models.Model):
    """
    Journal final d'un commit d'import (compte-rendu).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    batch = models.OneToOneField(ImportBatch, on_delete=models.CASCADE, related_name="commit_log")

    created_users = models.PositiveIntegerField(default=0)
    updated_users = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)

    duration_ms = models.PositiveIntegerField(default=0)

    preview_sample = models.JSONField(default=list, help_text="Extraits anonymisés (ex: 5 lignes).")

    committed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "core_import_commit_log"
        verbose_name = "Journal d'import"
        verbose_name_plural = "Journaux d'import"
        indexes = [
            models.Index(fields=["committed_at"], name="idx_iclog_committed"),
        ]
        ordering = ["-committed_at"]

    def __str__(self) -> str:
        return f"Commit {self.batch_id} — {self.committed_at:%Y-%m-%d %H:%M}"
