from django.utils.translation import gettext_lazy
import logging
from functools import wraps

from allauth.account.models import EmailAddress
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from kombu.exceptions import OperationalError
from credits.services import wallet_for

from .forms import DubbingForm
from .models import DubbingJob, DubbingLanguage
from .tasks import process_job
from .presentation import editor_context, studio_config, video_content_type

logger = logging.getLogger(__name__)


def verified_view(view):
    @login_required
    @never_cache
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not EmailAddress.objects.filter(user=request.user, email__iexact=request.user.email, verified=True).exists():
            return render(request, 'account/verified_email_required.html', status=403)
        return view(request, *args, **kwargs)
    return wrapped


def enqueue(pk):
    try:
        process_job.delay(str(pk))
    except (OperationalError, OSError) as error:
        logger.warning('Publication du doublage différée : %s', type(error).__name__)


@verified_view
@require_GET
def index(request):
    jobs = list(request.user.dubbing_jobs.prefetch_related('outputs').all()[:50])
    return render(request, 'studio/index.html', {'jobs': jobs, 'has_active_jobs': any(job.active for job in jobs),
        'target_language_count': DubbingLanguage.objects.filter(target=True).count()})


@verified_view
@require_http_methods(['GET', 'POST'])
def create(request):
    configured = settings.MURFDUB_ENABLED and bool(settings.MURFDUB_API_KEY)
    form = DubbingForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        if not configured:
            form.add_error(None, gettext_lazy('Le service de doublage n’est pas encore configuré.'))
        else:
            job = None
            try:
                with transaction.atomic():
                    get_user_model().objects.select_for_update().get(pk=request.user.pk)
                    existing = DubbingJob.objects.filter(pk=form.cleaned_data['submission_id']).first()
                    if existing:
                        if existing.user_id != request.user.pk:
                            raise Http404
                        return redirect('studio:detail', pk=existing.pk)
                    wallet = wallet_for(request.user)
                    count = request.user.dubbing_jobs.filter(status__in=['queued', 'waiting_murf', 'analyzing', 'submitting', 'processing', 'saving']).count()
                    if settings.CREDITS_ENABLED and (wallet.frozen or wallet.available_units < 60000 * len(form.cleaned_data['target_locales'])):
                        form.add_error(None, gettext_lazy('Rechargez votre portefeuille avant de lancer ce doublage. Il faut au moins un crédit disponible par langue.'))
                    elif count >= settings.STUDIO_MAX_ACTIVE_JOBS:
                        form.add_error(None, 'Attendez la fin de vos doublages en cours avant d’en lancer un nouveau.')
                    else:
                        uploaded = form.cleaned_data['video']
                        job = DubbingJob(id=form.cleaned_data['submission_id'], user=request.user,
                            title=form.cleaned_data['title'], original_name=uploaded.name[:255],
                            source_locale=form.cleaned_data['source_locale'], target_locales=form.cleaned_data['target_locales'],
                            credit_charge_required=settings.CREDITS_ENABLED)
                        job.source = uploaded
                        try:
                            job.save()
                        except Exception:
                            # FileField peut avoir écrit dans R2 avant un échec SQL.
                            if job.source and job.source._committed:
                                try:
                                    job.source.storage.delete(job.source.name)
                                except (BotoCoreError, ClientError, OSError):
                                    logger.warning('Nettoyage d’un import incomplet différé.')
                            raise
                        transaction.on_commit(lambda: enqueue(job.pk))
                if job:
                    return redirect('studio:detail', pk=job.pk)
            except (BotoCoreError, ClientError, OSError) as error:
                logger.warning('Import vidéo indisponible : %s', type(error).__name__)
                form.add_error('video', gettext_lazy('La vidéo n’a pas pu être enregistrée. Réessayez dans un instant.'))
    limit = settings.STUDIO_MAX_UPLOAD_BYTES
    return render(request, 'studio/create.html', {'form': form, 'configured': configured,
        'target_language_count': len(form.fields['target_locales'].choices),
        'upload_limit_mb': limit // (1024 ** 2) if limit else None,
        **editor_context(request.user, form=form), 'billing_enabled': settings.CREDITS_ENABLED})


@never_cache
@require_http_methods(['GET', 'POST'])
def legacy_create(request):
    # Preserve submissions from an already open form at the former address.
    if request.method == 'POST':
        return create(request)
    return redirect('studio:create')


@verified_view
@require_GET
def detail(request, pk):
    job = get_object_or_404(DubbingJob.objects.prefetch_related('outputs'), pk=pk, user=request.user)
    return render(request, 'studio/detail.html', {'job': job, **editor_context(request.user, job=job)})


@verified_view
@require_GET
def status(request, pk):
    job = get_object_or_404(DubbingJob, pk=pk, user=request.user)
    if request.GET.get('view') == 'studio':
        response = render(request, 'studio/_editor_state.html', {
            'job': job, 'studio_state': studio_config(request.user, job=job),
        })
    else:
        response = render(request, 'studio/_status.html', {'job': job})
    patch_vary_headers(response, ['HX-Request'])
    return response


@verified_view
@require_POST
def resume(request, pk):
    with transaction.atomic():
        job = get_object_or_404(DubbingJob.objects.select_for_update(), pk=pk, user=request.user)
        if job.status == 'review' and job.murf_job_id:
            job.status, job.attempts, job.error_message = 'processing', 0, ''
            job.next_check_at = None
            job.save(update_fields=['status', 'attempts', 'error_message', 'next_check_at', 'updated_at'])
            transaction.on_commit(lambda: enqueue(job.pk))
        elif job.status == 'failed' and job.error_code == 'INSUFFICIENT_USER_CREDITS' and not job.murf_job_id:
            job.status, job.error_message, job.error_code = 'queued', '', ''
            job.next_check_at, job.lease_until = None, None
            job.save(update_fields=['status', 'error_message', 'error_code', 'next_check_at', 'lease_until', 'updated_at'])
            transaction.on_commit(lambda: enqueue(job.pk))
    return redirect('studio:detail', pk=job.pk)


@verified_view
@require_GET
def download(request, pk, output_id, kind):
    job = get_object_or_404(DubbingJob, pk=pk, user=request.user)
    output = get_object_or_404(job.outputs, pk=output_id)
    if kind not in ('video', 'subtitles'):
        raise Http404
    field = getattr(output, kind)
    if not field:
        raise Http404
    return redirect(field.storage.url(field.name, expire=300, parameters={
        'ResponseContentDisposition': 'attachment',
    }))


@verified_view
@require_GET
def watch(request, pk, output_id=None):
    job = get_object_or_404(DubbingJob, pk=pk, user=request.user)
    if output_id is None:
        field = job.source
        content_type = video_content_type(field.name) if field else None
    else:
        output = get_object_or_404(job.outputs, pk=output_id)
        field, content_type = output.video, output.video_content_type
    if not content_type:
        raise Http404
    response = redirect(field.storage.url(field.name, expire=3600, parameters={
        'ResponseContentDisposition': 'inline',
        'ResponseContentType': content_type,
    }))
    response['Referrer-Policy'] = 'no-referrer'
    return response

