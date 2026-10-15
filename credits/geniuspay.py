"""API Marchand officielle : https://geniuspay.ci/docs/api (checkout hébergé)."""
from django.utils.translation import gettext_lazy
import hashlib
import hmac
import json
import time
from urllib.parse import quote, urlsplit

import requests
from django.core.exceptions import ImproperlyConfigured

from .config import payment_environment, public_url, value


class PaymentUnavailable(Exception):
    """Ne contient jamais le corps HTTP, les clés ou une URL privée."""

    def __init__(self, message, *, http_status=None, provider_code='', rejected_fields=()):
        super().__init__(message)
        self.http_status = http_status
        self.provider_code = provider_code
        self.rejected_fields = rejected_fields


class InvalidWebhookSignature(ValueError):
    pass


def configured():
    mode = payment_environment()
    return bool(value('GENIUSPAY_API_KEY').startswith(f'pk_{mode}_')
                and value('GENIUSPAY_API_SECRET').startswith(f'sk_{mode}_') and public_url())


def api(method, path, payload=None):
    mode = payment_environment()
    if not (value('GENIUSPAY_API_KEY').startswith(f'pk_{mode}_')
            and value('GENIUSPAY_API_SECRET').startswith(f'sk_{mode}_')):
        raise ImproperlyConfigured(gettext_lazy('Genius Pay n’est pas configuré.'))
    try:
        response = requests.request(method, 'https://geniuspay.ci/api/v1/merchant/' + path,
            headers={'X-API-Key': value('GENIUSPAY_API_KEY'), 'X-API-Secret': value('GENIUSPAY_API_SECRET')},
            json=payload, timeout=(5, 25), allow_redirects=False)
        if response.status_code not in (200, 201):
            code, fields = '', ()
            try:
                error_body = response.json()
                error = error_body.get('error') or {}
                known_codes = {'VALIDATION_ERROR', 'INVALID_API_KEY', 'INVALID_API_SECRET',
                    'UNAUTHORIZED', 'FORBIDDEN', 'RATE_LIMIT_EXCEEDED', 'TRANSACTION_NOT_FOUND',
                    'INSUFFICIENT_BALANCE', 'PAYMENT_FAILED', 'INVALID_AMOUNT', 'INVALID_CURRENCY',
                    'MISSING_API_KEY', 'MERCHANT_INACTIVE', 'PAYMENT_INIT_FAILED', 'COUNTRY_NOT_SUPPORTED'}
                if isinstance(error, dict) and error.get('code') in known_codes:
                    code = error['code']
                errors = error_body.get('errors') or (error.get('details') if isinstance(error, dict) else {}) or {}
                if isinstance(errors, dict):
                    fields = tuple(key for key in ('amount', 'currency', 'success_url', 'error_url',
                                                   'customer.email', 'metadata') if key in errors)
            except (ValueError, AttributeError, TypeError):
                pass
            raise PaymentUnavailable('Réponse de paiement indisponible.', http_status=response.status_code,
                                     provider_code=code, rejected_fields=fields)
        body = response.json()
        if body.get('success') is not True or not isinstance(body.get('data'), dict):
            raise PaymentUnavailable('Réponse de paiement invalide.')
        return body['data']
    except (requests.RequestException, ValueError, AttributeError) as error:
        raise PaymentUnavailable(gettext_lazy('Le service de paiement est indisponible.')) from None


def create_payment(purchase, return_path):
    user = purchase.wallet.user
    return_url = public_url() + return_path
    data = api('POST', 'payments', {
        'amount': int(purchase.price_usd), 'currency': 'USD',
        'description': f'Dublao — {purchase.quantity} crédits',
        'customer': {'name': user.get_full_name() or 'Utilisateur Dublao', 'email': user.email},
        'success_url': return_url, 'error_url': return_url,
        'metadata': {'order_id': str(purchase.pk), 'user_id': str(user.pk)},
    })
    url = safe_checkout_url(data.get('checkout_url', ''))
    return data, url


def safe_checkout_url(url):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        raise PaymentUnavailable('Lien de paiement invalide.') from None
    if (parsed.scheme != 'https' or parsed.hostname not in {'geniuspay.ci', 'pay.genius.ci'}
            or parsed.username or parsed.password or port not in (None, 443)
            or len(url) > 600):
        raise PaymentUnavailable('Lien de paiement invalide.')
    return url


def get_payment(reference):
    return api('GET', 'payments/' + quote(reference, safe=''))


def webhook_secret():
    name = 'GENIUSPAY_WEBHOOK_SECRET_LIVE' if payment_environment() == 'live' else 'GENIUSPAY_WEBHOOK_SECRET_SANDBOX'
    return value(name) or value('GENIUSPAY_WEBHOOK_SECRET')


def webhook_payload(body, signature, timestamp):
    secret = webhook_secret()
    if not secret:
        raise ImproperlyConfigured('Secret webhook manquant.')
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError('Notification expirée.')
        expected = hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise InvalidWebhookSignature('Signature incorrecte.')
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), dict):
            raise ValueError('Notification invalide.')
        return payload
    except (TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError('Notification invalide.') from None
