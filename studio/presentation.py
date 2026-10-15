"""Studio presentation, derived from persisted jobs rather than provider guesses."""
from django.utils.translation import gettext_lazy
from pathlib import Path
from botocore.exceptions import BotoCoreError, ClientError

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.templatetags.static import static
from django.urls import reverse

from credits.services import wallet_for
from .languages import flag_code, language_name
from .models import DubbingLanguage


def video_content_type(name):
    return {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm',
            '.mov': 'video/quicktime'}.get(Path(name).suffix.lower())


def studio_config(user, job=None, form=None):
    wallet = wallet_for(user)
    config = {
        'mode': 'project' if job else 'create', 'title': job.title if job else '',
        'availableUnits': wallet.available_units, 'reservedUnits': wallet.reserved_units, 'frozen': wallet.frozen,
        'reservationStatus': '', 'reservationUnits': 0, 'consumedUnits': 0,
        'billingEnabled': settings.CREDITS_ENABLED, 'versions': [],
        'originalUrl': '', 'filename': job.original_name if job else '',
        'durationMs': job.duration_ms if job else None, 'status': 'draft',
        'statusLabel': gettext_lazy('Nouveau projet'), 'errorMessage': '', 'resumeUrl': '',
        'sourceLabel': language_name(job.source_locale) if job and job.source_locale else gettext_lazy('Détection automatique'),
    }
    if not job:
        if form:
            config['title'] = form['title'].value() or ''
        return config
    config.update(status=job.status, statusLabel=job.get_status_display(), errorMessage=gettext_lazy(job.error_message))
    try:
        reservation = job.credit_reservation
        config.update(reservationStatus=reservation.status, reservationUnits=reservation.reserved_units,
                      consumedUnits=reservation.consumed_units)
    except ObjectDoesNotExist:
        pass
    if job.source and video_content_type(job.source.name):
        config['originalUrl'] = reverse('studio:original', args=[job.pk])
    if (job.status == 'review' and job.murf_job_id) or (
        job.status == 'failed' and job.error_code == 'INSUFFICIENT_USER_CREDITS' and not job.murf_job_id
    ):
        config['resumeUrl'] = reverse('studio:resume', args=[job.pk])
    outputs = {output.locale: output for output in job.outputs.all()}
    for locale in job.target_locales:
        output = outputs.get(locale)
        # A language is ready only once its own file has been saved.
        if output and output.video:
            state, label = 'ready', gettext_lazy('Terminé')
        elif (output and output.error_message) or job.status in ('failed', 'partial', 'completed'):
            state, label = 'failed', gettext_lazy('Échoué')
        elif job.status == 'review':
            state, label = 'review', gettext_lazy('À vérifier')
        elif job.status in ('processing', 'saving'):
            state, label = 'processing', gettext_lazy('En traitement')
        else:
            state, label = 'waiting', gettext_lazy('En attente')
        country = flag_code(locale)
        config['versions'].append({
            'locale': locale, 'name': language_name(locale), 'state': state, 'statusLabel': label,
            'flagUrl': static(f'studio/flags/{country}.svg') if country else '',
            'watchUrl': reverse('studio:watch', args=[job.pk, output.pk]) if output and output.video_content_type else '',
            'downloadUrl': reverse('studio:download', args=[job.pk, output.pk, 'video']) if output and output.video else '',
            'subtitleUrl': reverse('studio:download', args=[job.pk, output.pk, 'subtitles']) if output and output.subtitles else '',
            'errorMessage': output.error_message if output else '',
        })
    return config


def editor_context(user, job=None, form=None):
    config = studio_config(user, job, form)
    playable = config['originalUrl'] or next((v['watchUrl'] for v in config['versions'] if v['watchUrl']), '')
    avatar_url = ''
    try:
        if user.profile.avatar:
            avatar_url = user.profile.avatar.url
    except (BotoCoreError, ClientError, OSError, ObjectDoesNotExist):
        pass  # An unavailable avatar never prevents opening the studio.
    return {'editor_config': config, 'editor_has_player': not job or job.active or bool(playable),
            'editor_initial_url': playable, 'wallet': wallet_for(user), 'editor_avatar_url': avatar_url,
            'target_language_count': len(form.fields['target_locales'].choices) if form else DubbingLanguage.objects.filter(target=True).count()}
