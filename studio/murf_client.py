from contextlib import contextmanager

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from murf import MurfDub


@contextmanager
def murf_client():
    if not settings.MURFDUB_ENABLED or not settings.MURFDUB_API_KEY:
        raise ImproperlyConfigured('Configurer MURFDUB_API_KEY et MURFDUB_ENABLED.')
    # Aucun retry implicite des POST facturés, ni redirection de la clé API.
    with httpx.Client(timeout=90, follow_redirects=False) as transport:
        yield MurfDub(api_key=settings.MURFDUB_API_KEY, httpx_client=transport)
