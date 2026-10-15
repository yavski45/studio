from django.utils.translation import gettext_lazy
import logging
from datetime import timedelta
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import httpx
import requests
from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from murf.core.api_error import ApiError
from credits.services import InsufficientCredits, reserve_job, settle_job
from supervision.murf_alerts import observe_balance, key_fingerprint

from .downloads import save_remote_file
from .duration import video_duration_ms
from .models import DubbingJob, DubbingOutput
from .murf_client import murf_client

logger = logging.getLogger(__name__)
MURF_CREDIT_CODES = {'INSUFFICIENT_CREDITS', 'CREDITS_EXHAUSTED'}
FAILURES = {
    'INSUFFICIENT_CREDITS': gettext_lazy('Le service de doublage ne dispose plus de crédits. Contactez l’équipe de Dublao.'),
    'CREDITS_EXHAUSTED': gettext_lazy('Le service de doublage ne dispose plus de crédits. Contactez l’équipe Dublao.'),
    'LANGUAGE_NOT_SUPPORTED': gettext_lazy('Une langue sélectionnée n’est pas prise en charge.'),
    'SPEECH_NOT_PRESENT': gettext_lazy('Aucune parole exploitable n’a été détectée dans la vidéo.'),
    'SOURCE_LANGUAGE_MISMATCH': gettext_lazy('La langue sélectionnée ne correspond pas à la vidéo.'),
}


def update_job(pk, **fields):
    DubbingJob.objects.filter(pk=pk).update(updated_at=timezone.now(), **fields)


def credit_error_code(error):
    """Ne lit que les codes structurés ; aucun message externe n'est enregistré."""
    body = error.body
    if not isinstance(body, dict):
        return ''
    containers = [body] + [body[key] for key in ('error', 'detail', 'details') if isinstance(body.get(key), dict)]
    for container in containers:
        for field in ('code', 'error_code', 'failure_code', 'error'):
            code = container.get(field)
            if isinstance(code, str) and code in MURF_CREDIT_CODES:
                return code
    return ''


@transaction.atomic
def wait_for_murf_credits(job, rejected_provider_id=None):
    current = DubbingJob.objects.select_for_update().get(pk=job.pk)
    if rejected_provider_id:
        if rejected_provider_id not in current.murf_rejected_job_ids:
            current.murf_rejected_job_ids.append(rejected_provider_id)
        current.murf_job_id = None
    current.status, current.error_code = 'waiting_murf', 'INSUFFICIENT_MURF_CREDITS'
    current.error_message = gettext_lazy('Votre doublage est en attente temporaire. Il reprendra automatiquement dès que le service sera disponible. Vos crédits restent réservés et ne sont pas consommés.')
    current.lease_until = None
    current.next_check_at = timezone.now() + timedelta(minutes=5)
    current.save()


def finish_job(job, successful_locales, **fields):
    with transaction.atomic():
        settle_job(job, successful_locales)
        update_job(job.pk, **fields)


@shared_task(ignore_result=True)
def dispatch_jobs():
    """Outbox durable : reprend les envois non publiés et les contrôles interrompus."""
    now = timezone.now()
    DubbingJob.objects.filter(status='analyzing', lease_until__lt=now).update(
        status='queued', lease_until=None, updated_at=now,
    )  # Aucun POST Murf n’a encore été effectué pendant l’analyse.
    DubbingJob.objects.filter(status='submitting', lease_until__lt=now).update(
        status='review', lease_until=None, updated_at=now,
        error_message=gettext_lazy('L’envoi a été interrompu. Une vérification est nécessaire avant tout nouvel envoi.'),
    )
    due = DubbingJob.objects.filter(status__in=['queued', 'waiting_murf', 'processing', 'saving']).filter(
        Q(next_check_at__isnull=True) | Q(next_check_at__lte=now),
    ).filter(Q(lease_until__isnull=True) | Q(lease_until__lt=now))
    for pk in due.order_by('created_at').values_list('pk', flat=True)[:100]:
        process_job.delay(str(pk))


@shared_task(ignore_result=True)
def process_job(job_id):
    now = timezone.now()
    with transaction.atomic():
        job = DubbingJob.objects.select_for_update().filter(pk=job_id).first()
        if not job or job.status not in ('queued', 'waiting_murf', 'processing', 'saving'):
            return
        if (job.lease_until and job.lease_until > now) or (job.next_check_at and job.next_check_at > now):
            return
        submit = job.status in ('queued', 'waiting_murf') and not job.murf_job_id
        job.lease_until = now + timedelta(minutes=30)
        if submit:
            job.status = 'analyzing' if job.credit_charge_required else 'submitting'
        job.save(update_fields=['lease_until', 'status', 'updated_at'])
    if submit:
        if job.credit_charge_required:
            try:
                duration_ms = job.duration_ms or video_duration_ms(job.source)
                update_job(job.pk, duration_ms=duration_ms)
                with transaction.atomic():
                    reserve_job(job, duration_ms, 'minute')
                    update_job(job.pk, status='submitting')
            except InsufficientCredits:
                update_job(job.pk, status='failed', lease_until=None, error_code='INSUFFICIENT_USER_CREDITS',
                    error_message=gettext_lazy('Vos crédits sont insuffisants pour cette durée et ces langues. Rechargez votre portefeuille puis reprenez ce doublage.'))
                return
            except (BotoCoreError, ClientError, OSError, ValueError, ImproperlyConfigured):
                finish_job(job, [], status='failed', lease_until=None, error_code='DURATION_UNAVAILABLE',
                    error_message=gettext_lazy('La durée de la vidéo n’a pas pu être vérifiée. Aucun doublage n’a été envoyé et aucun crédit n’a été consommé.'))
                return
        try:
            source_url = job.source.storage.url(job.source.name, expire=3600)
            with murf_client() as client:
                options = dict(target_locales=job.target_locales, file_url=source_url,
                               file_name=job.original_name, priority='NORMAL', request_options={'max_retries': 0})
                if job.source_locale:
                    options['source_locale'] = job.source_locale
                result = client.dubbing.jobs.create(**options)
            if not result.job_id or len(result.job_id) > 200 or result.job_id in job.murf_rejected_job_ids:
                raise ValueError('Réponse de création incomplète.')
            update_job(job.pk, murf_job_id=result.job_id, status='processing', lease_until=None,
                       next_check_at=now + timedelta(seconds=30), error_message='', error_code='',
                       provider_status='', attempts=0, processing_started_at=timezone.now())
        except ApiError as error:
            rejected = error.status_code in (400, 401, 402, 403, 404, 422, 429)
            if rejected and credit_error_code(error):
                wait_for_murf_credits(job)
                return
            message = gettext_lazy('Le service a refusé ce doublage. Vérifiez sa configuration.') if rejected else gettext_lazy('La réception de la vidéo est incertaine. Contactez l’équipe Dublao avant de relancer.')
            if rejected:
                finish_job(job, [], status='failed', lease_until=None, error_message=message)
            else:
                update_job(job.pk, status='review', lease_until=None, error_message=message)
            logger.warning('Création Murf : %s (HTTP %s)', type(error).__name__, error.status_code)
        except (httpx.HTTPError, BotoCoreError, ClientError, OSError, ValueError, ImproperlyConfigured) as error:
            update_job(job.pk, status='review', lease_until=None,
                       error_message=gettext_lazy('L’envoi n’a pas pu être confirmé. Contactez l’équipe Dublao avant de relancer.'))
            logger.warning('Création Murf interrompue : %s', type(error).__name__)
        return

    try:
        balance_observed_at, balance_key = timezone.now(), key_fingerprint()
        with murf_client() as client:
            result = client.dubbing.jobs.get_status(job_id=job.murf_job_id, request_options={'max_retries': 0})
        if result.job_id != job.murf_job_id:
            raise ValueError('Identifiant de résultat incohérent.')
        observe_balance(getattr(result, 'credits_remaining', None), balance_observed_at, balance_key)
        provider_status = result.status.upper().replace(' ', '_')
        update_job(job.pk, provider_status=provider_status[:100], provider_credits_used=result.credits_used)
        if provider_status == 'FAILED':
            code = result.failure_code if result.failure_code in FAILURES else 'PROVIDER_FAILED'
            if code in MURF_CREDIT_CODES:
                produced = any((getattr(detail, 'status', '') or '').upper() == 'COMPLETED'
                               or getattr(detail, 'download_url', None) for detail in result.download_details or [])
                if result.credits_used not in (None, 0) or produced or job.outputs.exclude(video='').exists():
                    update_job(job.pk, status='review', lease_until=None,
                        error_code='MURF_CREDITS_REVIEW',
                        error_message=gettext_lazy('Une vérification est nécessaire avant de reprendre ce doublage. Vos crédits restent réservés.'))
                else:
                    wait_for_murf_credits(job, rejected_provider_id=job.murf_job_id)
                return
            finish_job(job, [], status='failed', lease_until=None, error_code=code,
                       error_message=FAILURES.get(code, gettext_lazy('Le doublage a échoué. Contactez l’équipe Dublao.')))
            return
        if provider_status not in ('COMPLETED', 'PARTIALLY_COMPLETED'):
            if now - (job.processing_started_at or job.created_at) > timedelta(hours=48):
                update_job(job.pk, status='review', lease_until=None,
                           error_message=gettext_lazy('Le traitement dure plus longtemps que prévu. Une vérification est nécessaire.'))
            else:
                update_job(job.pk, lease_until=None, next_check_at=now + timedelta(seconds=30))
            return
        update_job(job.pk, status='saving')
        successful = set()
        locale_aliases = {locale.replace('-', '_'): locale for locale in job.target_locales}
        for detail in result.download_details or []:
            locale = locale_aliases.get((detail.locale or '').replace('-', '_'))
            if locale not in job.target_locales:
                continue
            output, _ = DubbingOutput.objects.get_or_create(job=job, locale=locale)
            if (detail.status or '').upper() != 'COMPLETED' or not detail.download_url:
                output.error_message = gettext_lazy('Cette langue n’a pas pu être doublée.')
                output.save(update_fields=['error_message'])
                continue
            extension = PurePosixPath(urlsplit(detail.download_url).path).suffix.lower()
            if extension not in ('.mp4', '.mov', '.mkv', '.avi', '.webm', '.zip', '.mp3', '.wav', '.aac'):
                extension = '.mp4'
            prefix = f'{job.user_id}/{job.pk}/{locale}'
            save_remote_file(detail.download_url, output.video, prefix + extension)
            if detail.download_srt_url:
                save_remote_file(detail.download_srt_url, output.subtitles, prefix + '.srt')
            output.error_message = ''
            output.save(update_fields=['error_message'])
            successful.add(locale)
        if successful == set(job.target_locales):
            status, message = 'completed', ''
        elif provider_status == 'PARTIALLY_COMPLETED' and successful:
            status, message = 'partial', gettext_lazy('Certaines langues n’ont pas pu être doublées. Les résultats disponibles sont conservés.')
        elif provider_status == 'PARTIALLY_COMPLETED':
            status, message = 'failed', gettext_lazy('Aucun résultat exploitable n’a été reçu.')
        else:
            raise ValueError('Résultats encore incomplets.')
        finish_job(job, successful, status=status, error_message=message, lease_until=None, next_check_at=None)
    except (ApiError, httpx.HTTPError, requests.RequestException, BotoCoreError, ClientError,
            OSError, ValueError, ImproperlyConfigured) as error:
        attempts = job.attempts + 1
        review = attempts >= 50 or now - (job.processing_started_at or job.created_at) > timedelta(hours=48)
        update_job(job.pk, attempts=attempts, lease_until=None,
                   status='review' if review else job.status,
                   next_check_at=now + timedelta(seconds=min(30 * 2 ** min(attempts, 4), 600)),
                   error_message=gettext_lazy('La récupération des résultats nécessite une vérification.') if review else
                   gettext_lazy('Le service est momentanément indisponible. Une nouvelle vérification est prévue.'))
        logger.warning('Contrôle Murf ou copie R2 : %s', type(error).__name__)
