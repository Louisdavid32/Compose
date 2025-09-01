# core/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from core.models.establishment import Establishment
import hashlib
import uuid

@receiver(pre_save, sender=Establishment)
def generate_tenant_id(sender, instance, **kwargs):
    if instance.tenant_id is None:  # Générer seulement si non défini
        # Combiner name et email pour le hachage
        data = f"{instance.name}{instance.email}".encode('utf-8')
        # Générer un hachage SHA-256
        hash_object = hashlib.sha256(data)
        # Convertir les 16 premiers octets du hachage en UUID
        tenant_id = uuid.UUID(bytes=hash_object.digest()[:16])
        instance.tenant_id = tenant_id