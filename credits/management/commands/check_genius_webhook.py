import hashlib
import hmac
import json
import time
import uuid
import requests

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from credits.views import webhook
from credits.geniuspay import webhook_secret
from credits.config import payment_environment


class Command(BaseCommand):
    help = 'Vérifie localement webhook.test avec le secret configuré, sans API externe ni mouvement de crédits.'

    def add_arguments(self, parser):
        parser.add_argument('--http-local', action='store_true', help='Vérifier aussi le serveur local sur 127.0.0.1:8000.')

    def handle(self, *args, **options):
        environment = payment_environment()
        secret = webhook_secret()
        if not secret:
            raise CommandError('Le secret du mode actif est absent.')
        timestamp = str(int(time.time()))
        body = json.dumps({'id': str(uuid.uuid4()), 'event': 'webhook.test', 'timestamp': int(timestamp),
            'data': {'object': 'webhook.test', 'message': 'Vérification locale Dublao'},
            'environment': environment}, ensure_ascii=False, separators=(',', ':')).encode()
        signature = hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        request = RequestFactory().post('/credits/webhook/geniuspay/', body, content_type='application/json',
            HTTP_X_WEBHOOK_SIGNATURE=signature, HTTP_X_WEBHOOK_TIMESTAMP=timestamp,
            HTTP_X_WEBHOOK_EVENT='webhook.test', HTTP_X_WEBHOOK_ENVIRONMENT=environment)
        response = webhook(request)
        if response.status_code != 200:
            raise CommandError(f'Vérification non confirmée (HTTP {response.status_code}).')
        self.stdout.write(self.style.SUCCESS(f'webhook.test : HTTP 200 ({environment}). Aucun crédit modifié.'))
        if options['http_local']:
            try:
                result = requests.post('http://127.0.0.1:8000/credits/webhook/geniuspay/', data=body,
                    headers={'Content-Type': 'application/json', 'X-Webhook-Signature': signature,
                             'X-Webhook-Timestamp': timestamp, 'X-Webhook-Event': 'webhook.test',
                             'X-Webhook-Environment': environment},
                    timeout=(3, 5), allow_redirects=False)
            except requests.RequestException:
                raise CommandError('Serveur local inaccessible.') from None
            if result.status_code != 200:
                raise CommandError(f'Serveur local : HTTP {result.status_code}.')
            self.stdout.write(self.style.SUCCESS('Serveur local : HTTP 200. Aucun crédit modifié.'))
