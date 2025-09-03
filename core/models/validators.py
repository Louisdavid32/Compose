"""
Validators réutilisables (sécurité, qualité des données).
- Taille des fichiers (logo)
- Extension d'image autorisée
- Téléphone E.164
- Code pays ISO-3166-1 alpha-2
"""

import re
from django.core.exceptions import ValidationError

# --- Fichier/logo ---

def validate_file_size(file, max_mb: int = 3) -> None:
    """
    Refuse les fichiers trop volumineux (défaut: 3 Mo).
    """
    if file and file.size > max_mb * 1024 * 1024:
        raise ValidationError(f"Le fichier dépasse {max_mb} Mo.")

ALLOWED_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg")

def validate_image_extension(file) -> None:
    """
    Vérifie l'extension (contrôle de base côté serveur).
    Pour un contrôle plus strict, activer une validation PIL/MIME au niveau du service d'upload.
    """
    name = (file.name or "").lower()
    if not any(name.endswith(ext) for ext in ALLOWED_IMAGE_EXT):
        raise ValidationError("Format d'image non supporté (png, jpg, jpeg, webp, svg).")

# --- Téléphone & pays ---

E164_REGEX = re.compile(r"^\+?[1-9]\d{7,14}$")  # ITU E.164 8..15 chiffres

def validate_phone_e164(value: str) -> None:
    """
    Valide un numéro au format E.164 (ex: +2376XXXXXXXX).
    """
    if value and not E164_REGEX.match(value):
        raise ValidationError("Numéro invalide (format E.164 requis).")

ISO2_REGEX = re.compile(r"^[A-Z]{2}$")

def validate_iso_country(value: str) -> None:
    """
    Valide un code pays ISO-3166-1 alpha-2 (2 lettres majuscules).
    """
    if not value or not ISO2_REGEX.match(value):
        raise ValidationError('Utiliser un code pays ISO-3166-1 alpha-2 (ex: "CM", "FR").')

# --- Afrique centrale (CEMAC) ---

CENTRAL_AFRICA_ISO2 = {"CM", "GA", "TD", "CF", "CG", "GQ"}  # Cameroun, Gabon, Tchad, RCA, Congo, Guinée équatoriale
CENTRAL_AFRICA_E164_PREFIXES = {"+237", "+241", "+235", "+236", "+242", "+240"}

def validate_central_africa_country(value: str) -> None:
    """
    Accepte uniquement les codes ISO-3166-1 alpha-2 des 6 pays d'Afrique centrale (CEMAC).
    """
    v = (value or "").strip().upper()
    if v not in CENTRAL_AFRICA_ISO2:
        raise ValidationError(
            f"Pays non autorisé. Utiliser l’un de: {', '.join(sorted(CENTRAL_AFRICA_ISO2))}."
        )

def validate_central_africa_phone(value: str) -> None:
    """
    Valide un numéro E.164 ET vérifie que le préfixe appartient aux 6 pays CEMAC.
    (Accepte l'absence de '+', on normalise en interne)
    """
    if not value:
        return
    # Validation E.164 (existant)
    validate_phone_e164(value)

    normalized = value if value.startswith("+") else f"+{value}"
    if not any(normalized.startswith(pfx) for pfx in CENTRAL_AFRICA_E164_PREFIXES):
        raise ValidationError(
            "Numéro hors zone CEMAC. Préfixe attendu parmi: "
            + ", ".join(sorted(CENTRAL_AFRICA_E164_PREFIXES))
        )


# --- Année scolaire ---
SCHOOL_YEAR_RE = re.compile(r"^(20\d{2})-(20\d{2})$")  # ex: 2024-2025

def validate_school_year(value: str) -> None:
    """
    Valide une année scolaire au format 'YYYY-YYYY' avec année2 = année1 + 1.
    Exemples valides: 2023-2024, 2024-2025.
    """
    if not value:
        raise ValidationError("L'année scolaire est requise (ex: 2024-2025).")
    m = SCHOOL_YEAR_RE.match(value.strip())
    if not m:
        raise ValidationError('Format invalide. Utiliser "YYYY-YYYY" (ex: 2024-2025).')
    start, end = int(m.group(1)), int(m.group(2))
    if end - start != 1:
        raise ValidationError("Année scolaire incohérente: la deuxième année doit être la première + 1.")
    if not (2000 <= start <= 2100):
        raise ValidationError("Année scolaire hors plage autorisée (2000-2100).")
