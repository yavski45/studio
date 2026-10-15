"""Stockage privé des fichiers utilisateurs dans Cloudflare R2."""

from django.core.exceptions import ImproperlyConfigured
from storages.backends.s3 import S3Storage


class PrivateR2Storage(S3Storage):
    def __init__(self, **kwargs):
        required = ('access_key', 'secret_key', 'bucket_name', 'endpoint_url')
        missing = [name for name in required if not kwargs.get(name)]
        if missing:
            raise ImproperlyConfigured(
                'Configuration R2 incomplète : compléter R2_ACCOUNT_ID (ou '
                'R2_ENDPOINT_URL), R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY et '
                'R2_BUCKET_NAME dans .env.'
            )
        if not kwargs['endpoint_url'].startswith('https://'):
            raise ImproperlyConfigured('R2_ENDPOINT_URL doit utiliser HTTPS.')
        super().__init__(**kwargs)
