from datetime import timedelta

import httpx
from celery import shared_task
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from murf.core.api_error import ApiError

from studio.models import DubbingJob
from studio.murf_client import murf_client
from .models import MurfCreditStatus
from .murf_alerts import key_fingerprint, observe_balance


@shared_task(ignore_result=True)
def refresh_murf_credits():
    now = timezone.now()
    fingerprint = key_fingerprint()
    with transaction.atomic():
        row, _ = MurfCreditStatus.objects.get_or_create(pk=1)
        row = MurfCreditStatus.objects.select_for_update().get(pk=row.pk)
        if row.refresh_lease_until and row.refresh_lease_until > now:
            return
        if row.key_fingerprint != fingerprint:
            row.credits_remaining, row.checked_at, row.observed_at = None, None, None
        row.key_fingerprint, row.refresh_lease_until = fingerprint, now + timedelta(minutes=3)
        row.save()
    error = ''
    try:
        job = DubbingJob.objects.exclude(murf_job_id__isnull=True).exclude(murf_job_id='').order_by('-created_at').first()
        if not job:
            error = 'NO_JOB'
        else:
            with murf_client() as client:
                result = client.dubbing.jobs.get_status(job_id=job.murf_job_id, request_options={'max_retries': 0})
            if result.job_id != job.murf_job_id:
                raise ValueError
            credits = getattr(result, 'credits_remaining', None)
            if isinstance(credits, bool) or not isinstance(credits, int) or credits < 0:
                error = 'BALANCE_UNAVAILABLE'
            else:
                observe_balance(credits, now, fingerprint)
    except (ApiError, httpx.HTTPError, OSError, ValueError, ImproperlyConfigured):
        error = 'PROVIDER_UNAVAILABLE'
    finally:
        MurfCreditStatus.objects.filter(pk=1, key_fingerprint=fingerprint,
            refresh_lease_until=now + timedelta(minutes=3)).update(refresh_lease_until=None, error_code=error)
