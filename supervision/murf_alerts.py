import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import MurfCreditStatus


def key_fingerprint():
    return hashlib.sha256((settings.MURFDUB_API_KEY or '').encode()).hexdigest()


@transaction.atomic
def observe_balance(credits, observed_at, fingerprint=None):
    if isinstance(credits, bool) or not isinstance(credits, int) or not 0 <= credits <= 9223372036854775807:
        return
    fingerprint = fingerprint or key_fingerprint()
    if fingerprint != key_fingerprint():
        return
    row, _ = MurfCreditStatus.objects.get_or_create(pk=1)
    row = MurfCreditStatus.objects.select_for_update().get(pk=row.pk)
    if row.key_fingerprint == fingerprint and row.observed_at and row.observed_at > observed_at:
        return
    row.key_fingerprint, row.credits_remaining = fingerprint, credits
    row.observed_at, row.checked_at, row.error_code = observed_at, timezone.now(), ''
    row.save(update_fields=['key_fingerprint', 'credits_remaining', 'observed_at', 'checked_at', 'error_code'])


def alert_context():
    from studio.models import DubbingJob
    waiting = DubbingJob.objects.filter(status='waiting_murf').count()
    row = MurfCreditStatus.objects.filter(pk=1).first()
    if not row or row.key_fingerprint != key_fingerprint():
        return {'level': 'unknown', 'remaining': None, 'threshold': row.threshold if row else 20, 'checked_at': None, 'waiting_jobs': waiting}
    remaining = row.credits_remaining
    level = ('unknown' if remaining is None else 'empty' if remaining == 0
             else 'low' if remaining <= row.threshold else 'ok')
    return {'level': level, 'remaining': remaining, 'threshold': row.threshold,
            'waiting_jobs': waiting,
            'checked_at': row.checked_at, 'error': row.error_code,
            'stale': not row.checked_at or row.checked_at < timezone.now() - timedelta(minutes=15)}
