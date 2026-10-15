"""Configuration Genius Pay, avec les noms du guide et de l'API marchand."""
import os

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def value(name, default=''):
    return getattr(settings, name, os.getenv(name, default))


def payment_environment():
    names = ('GENIUSPAY_ENVIRONMENT', 'GENIUSPAY_MODE')
    # Les réglages Django explicites priment sur .env (y compris en test).
    modes = [getattr(settings, name) for name in names if hasattr(settings, name)]
    if not modes:
        modes = [os.getenv(name, '') for name in names]
    modes = {str(mode).strip().lower() for mode in modes if mode}
    if len(modes) > 1 or (modes and not modes <= {'live', 'sandbox'}):
        raise ImproperlyConfigured('Le mode Genius Pay doit être live ou sandbox et ses noms doivent concorder.')
    return next(iter(modes), 'sandbox')


def public_url():
    return value('PAYMENT_PUBLIC_URL').strip().rstrip('/')


def accepts_xof_conversion():
    return str(value('GENIUSPAY_ACCEPT_XOF_CONVERSION', 'false')).strip().lower() in {'true', '1', 'yes'}
