from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.files.storage import InMemoryStorage
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from murf.core.api_error import ApiError

from credits.models import CreditEntry
from credits.services import grant_credits, reserve_job
from supervision.murf_alerts import alert_context
from .models import DubbingJob
from .tasks import dispatch_jobs, process_job


@override_settings(MURFDUB_ENABLED=True, MURFDUB_API_KEY='waiting-test-key')
class MurfWaitingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='murf-waiting', email='waiting@example.test')
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True)
        grant_credits(self.user, 5, 'waiting-funds')
        self.job = DubbingJob.objects.create(user=self.user, title='En attente', source='source.mp4',
            original_name='source.mp4', target_locales=['en_US', 'fr_FR'], duration_ms=61000,
            credit_charge_required=True)

    def factory(self, client):
        @contextmanager
        def factory():
            yield client
        return patch('studio.tasks.murf_client', factory)

    def wallet(self):
        self.user.credit_wallet.refresh_from_db()
        return self.user.credit_wallet

    def test_definite_credit_rejection_waits_then_resumes_without_second_reservation(self):
        client = Mock()
        client.dubbing.jobs.create.side_effect = [
            ApiError(status_code=403, body={'error': {'code': 'INSUFFICIENT_CREDITS'}}),
            SimpleNamespace(job_id='recharged-murf-job')]
        with self.factory(client), patch.object(InMemoryStorage, 'url', return_value='https://storage.example/source.mp4'):
            process_job(str(self.job.pk))
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, 'waiting_murf')
            self.assertTrue(self.job.active)
            self.assertEqual(self.wallet().available_credits, 1)
            self.assertEqual(self.wallet().reserved_credits, 4)
            process_job(str(self.job.pk))  # Pas de nouvelle tentative avant cinq minutes.
            self.assertEqual(client.dubbing.jobs.create.call_count, 1)
            DubbingJob.objects.filter(pk=self.job.pk).update(next_check_at=None,
                created_at=timezone.now() - timedelta(days=5))
            process_job(str(self.job.pk))
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, 'processing')
            self.assertEqual(self.job.error_code, '')
            self.assertIsNotNone(self.job.processing_started_at)
            self.assertEqual(self.wallet().available_credits, 1)
            self.assertEqual(CreditEntry.objects.filter(kind='reserve').count(), 1)
            self.assertEqual(CreditEntry.objects.filter(kind='settle').count(), 0)
            client.dubbing.jobs.get_status.return_value = SimpleNamespace(job_id='recharged-murf-job',
                status='PROCESSING', credits_used=None, credits_remaining=100)
            DubbingJob.objects.filter(pk=self.job.pk).update(next_check_at=None)
            process_job(str(self.job.pk))
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, 'processing')  # L'attente n'a pas consommé le délai de traitement.
            self.assertEqual(client.dubbing.jobs.create.call_count, 2)
            client.dubbing.jobs.get_status.return_value = SimpleNamespace(job_id='recharged-murf-job',
                status='COMPLETED', credits_used=4, credits_remaining=96,
                download_details=[SimpleNamespace(locale=locale, status='COMPLETED',
                    download_url='https://cdn.murf.ai/result.mp4', download_srt_url=None)
                    for locale in self.job.target_locales])
            def save_video(url, field, name):
                field.save(name, ContentFile(b'test-video'), save=True)
            DubbingJob.objects.filter(pk=self.job.pk).update(next_check_at=None)
            with patch('studio.tasks.save_remote_file', side_effect=save_video):
                process_job(str(self.job.pk))
                process_job(str(self.job.pk))
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, 'completed')
            self.assertEqual(self.wallet().reserved_credits, 0)
            self.assertEqual(self.wallet().available_credits, 1)
            self.assertEqual(CreditEntry.objects.filter(kind='settle').count(), 1)

    def test_credit_word_in_server_error_is_not_safe_to_resubmit(self):
        client = Mock()
        client.dubbing.jobs.create.side_effect = ApiError(status_code=500, body={'code': 'CREDITS_EXHAUSTED'})
        with self.factory(client), patch.object(InMemoryStorage, 'url', return_value='https://storage.example/source.mp4'):
            process_job(str(self.job.pk))
            process_job(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'review')
        client.dubbing.jobs.create.assert_called_once()

    def test_failed_provider_job_without_work_is_archived_and_waits(self):
        reserve_job(self.job, 61000, 'minute')
        self.job.status, self.job.murf_job_id = 'processing', 'rejected-murf-job'
        self.job.save()
        client = Mock()
        client.dubbing.jobs.get_status.return_value = SimpleNamespace(job_id='rejected-murf-job',
            status='FAILED', credits_used=0, credits_remaining=0, failure_code='CREDITS_EXHAUSTED', download_details=[])
        with self.factory(client):
            process_job(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'waiting_murf')
        self.assertIsNone(self.job.murf_job_id)
        self.assertEqual(self.job.murf_rejected_job_ids, ['rejected-murf-job'])
        self.assertEqual(self.wallet().reserved_credits, 4)
        self.assertEqual(alert_context()['waiting_jobs'], 1)
        client.dubbing.jobs.create.assert_not_called()

    def test_charge_or_output_on_failed_job_requires_review(self):
        reserve_job(self.job, 61000, 'minute')
        self.job.status, self.job.murf_job_id = 'processing', 'charged-murf-job'
        self.job.save()
        client = Mock()
        client.dubbing.jobs.get_status.return_value = SimpleNamespace(job_id='charged-murf-job',
            status='FAILED', credits_used=2, credits_remaining=0, failure_code='INSUFFICIENT_CREDITS', download_details=[])
        with self.factory(client):
            process_job(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'review')
        self.assertEqual(self.job.murf_job_id, 'charged-murf-job')
        self.assertEqual(self.wallet().reserved_credits, 4)

    @patch('studio.tasks.process_job.delay')
    def test_dispatcher_and_user_page_support_waiting_status(self, delay):
        self.job.status = 'waiting_murf'
        self.job.save()
        dispatch_jobs()
        delay.assert_called_once_with(str(self.job.pk))
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('studio:detail', args=[self.job.pk])), 'En attente du service')
