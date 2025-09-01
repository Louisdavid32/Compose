import random
import string
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache

def generate_otp(user, purpose='activation'):
    otp = ''.join(random.choices(string.digits, k=6))
    cache_key = f"otp_{purpose}_{user.id}"
    cache.set(cache_key, otp, timeout=300)  # OTP valide 5 minutes
    print(f"Envoi SMS à {getattr(user, 'phone_number', user.email)}: Votre code OTP de {purpose} est : {otp}")
    return otp

def verify_otp(user, otp, purpose='activation'):
    cache_key = f"otp_{purpose}_{user.id}"
    stored_otp = cache.get(cache_key)
    if stored_otp and stored_otp == otp:
        cache.delete(cache_key)
        return True
    return False
