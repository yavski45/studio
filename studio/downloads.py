"""Copie des sorties temporaires Murf vers le stockage privé, sans clé API."""
import ipaddress
import socket
import time
from tempfile import TemporaryFile
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings
from django.core.files import File


def validate_download_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Adresse de téléchargement refusée.')
    if not any(host == pattern.lstrip('.') or (pattern.startswith('.') and host.endswith(pattern)) for pattern in settings.STUDIO_DOWNLOAD_HOSTS):
        raise ValueError('Hôte de téléchargement non autorisé.')
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ValueError('Adresse réseau privée refusée.')


def save_remote_file(url, field, name):
    if field:
        return
    started = time.monotonic()
    with requests.Session() as session:
        session.trust_env = False
        for _ in range(4):
            validate_download_url(url)
            with session.get(url, stream=True, timeout=(10, 60), allow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers['Location'])
                    continue
                response.raise_for_status()
                size = 0
                with TemporaryFile() as downloaded:
                    for chunk in response.iter_content(1024 * 1024):
                        size += len(chunk)
                        if time.monotonic() - started > 600:
                            raise ValueError('Téléchargement trop long.')
                        downloaded.write(chunk)
                    if not size:
                        raise ValueError('Résultat vide.')
                    downloaded.seek(0)
                    field.save(name, File(downloaded), save=False)
                    try:
                        field.instance.save(update_fields=[field.field.name])
                    except Exception:
                        field.storage.delete(field.name)
                        raise
                return
        raise ValueError('Trop de redirections.')
