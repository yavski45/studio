from django.utils.translation import gettext_lazy
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.templatetags.static import static

from .languages import flag_code, language_name


def source_path(instance, filename):
    return f'dubbing/{instance.user_id}/{instance.pk}/source{Path(filename).suffix.lower()}'


class DubbingLanguage(models.Model):
    locale = models.CharField(max_length=32, primary_key=True)
    name = models.CharField(max_length=100)
    source = models.BooleanField(default=False)
    target = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def display_name(self):
        return language_name(self.locale, self.name)


class DubbingJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', gettext_lazy('En attente')
        WAITING_MURF = 'waiting_murf', gettext_lazy('En attente du service')
        ANALYZING = 'analyzing', gettext_lazy('Analyse de la vidéo')
        SUBMITTING = 'submitting', gettext_lazy('Envoi au service de doublage')
        PROCESSING = 'processing', gettext_lazy('Doublage en cours')
        SAVING = 'saving', gettext_lazy('Sauvegarde des résultats')
        COMPLETED = 'completed', gettext_lazy('Terminé')
        PARTIAL = 'partial', gettext_lazy('Partiellement terminé')
        FAILED = 'failed', gettext_lazy('Échec')
        REVIEW = 'review', gettext_lazy('Vérification nécessaire')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='dubbing_jobs')
    title = models.CharField(max_length=120)
    source = models.FileField(upload_to=source_path, max_length=500)
    original_name = models.CharField(max_length=255)
    source_locale = models.CharField(max_length=32, blank=True)
    target_locales = models.JSONField(default=list)
    credit_charge_required = models.BooleanField(default=False)
    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)
    murf_job_id = models.CharField(max_length=200, blank=True, null=True, unique=True)
    murf_rejected_job_ids = models.JSONField(default=list, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    provider_status = models.CharField(max_length=100, blank=True)
    provider_credits_used = models.PositiveBigIntegerField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    lease_until = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'next_check_at'])]

    @property
    def active(self):
        return self.status in ('queued', 'waiting_murf', 'analyzing', 'submitting', 'processing', 'saving')


class DubbingOutput(models.Model):
    job = models.ForeignKey(DubbingJob, on_delete=models.CASCADE, related_name='outputs')
    locale = models.CharField(max_length=32)
    video = models.FileField(upload_to='dubbing/results/', max_length=500, blank=True)
    subtitles = models.FileField(upload_to='dubbing/results/', max_length=500, blank=True)
    error_message = models.CharField(max_length=500, blank=True)

    @property
    def display_name(self):
        return language_name(self.locale)

    @property
    def flag_url(self):
        country = flag_code(self.locale)
        return static(f'studio/flags/{country}.svg') if country else None

    @property
    def video_content_type(self):
        return {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm',
                '.mov': 'video/quicktime'}.get(Path(self.video.name).suffix.lower()) if self.video else None

    class Meta:
        constraints = [models.UniqueConstraint(fields=['job', 'locale'], name='unique_dubbing_output_locale')]



