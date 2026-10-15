import uuid
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError
from murf.core.api_error import ApiError

from .forms import DubbingForm
from .models import DubbingJob, DubbingOutput
from .tasks import dispatch_jobs, process_job


def video():
    return SimpleUploadedFile('test.mp4', b'\x00\x00\x00\x18ftypisom' + b'\x00' * 40, content_type='video/mp4')


def response(status='COMPLETED', details=None, **kwargs):
    return SimpleNamespace(job_id='murf-test', status=status, credits_used=2,
        failure_code=None, download_details=details or [], **kwargs)


@override_settings(MURFDUB_ENABLED=True, MURFDUB_API_KEY='test-key', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PipelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='studio-user', email='studio@example.com', password='test')
        self.other = get_user_model().objects.create_user(username='other', email='other@example.com')
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True)
        self.client.force_login(self.user)
        self.job = DubbingJob.objects.create(user=self.user, title='Tutoriel', source='test.mp4', original_name='test.mp4', target_locales=['en_US'])

    def post_data(self, token=None):
        return {'submission_id': str(token or uuid.uuid4()), 'title': 'Ma vidéo', 'source_locale': 'fr_FR', 'target_locales': ['en_US'], 'video': video(), 'consent': 'on'}

    def provider(self, result=None, error=None):
        client = Mock()
        client.dubbing.jobs.create.return_value = SimpleNamespace(job_id='murf-test')
        client.dubbing.jobs.get_status.return_value = result or response('PROCESSING')
        if error:
            client.dubbing.jobs.create.side_effect = error
        @contextmanager
        def factory():
            yield client
        return client, patch('studio.tasks.murf_client', factory)

    def prepare_poll(self):
        self.job.status = 'processing'
        self.job.murf_job_id = 'murf-test'
        self.job.save()

    def test_form_rejects_renamed_non_video_and_same_language(self):
        data = self.post_data()
        form = DubbingForm(data, {'video': SimpleUploadedFile('bad.mp4', b'not video')})
        self.assertFalse(form.is_valid())
        self.assertIn('video', form.errors)
        data['target_locales'] = ['fr_FR']
        form = DubbingForm(data, {'video': video()})
        self.assertFalse(form.is_valid())
        self.assertIn('target_locales', form.errors)

    @override_settings(STUDIO_MAX_UPLOAD_BYTES=8)
    def test_upload_limit(self):
        form = DubbingForm(self.post_data(), {'video': video()})
        self.assertFalse(form.is_valid())
        self.assertIn('video', form.errors)

    @override_settings(STUDIO_MAX_UPLOAD_BYTES=0)
    def test_unlimited_upload_accepts_declared_size_above_one_gib(self):
        uploaded = video()
        uploaded.size = 5 * 1024 ** 3
        form = DubbingForm(self.post_data(), {'video': uploaded})
        self.assertTrue(form.is_valid(), form.errors)
        page = self.client.get(reverse('studio:create'))
        self.assertNotContains(page, 'Mo maximum')

    def test_requires_consent_and_known_languages(self):
        data = self.post_data()
        data['target_locales'] = ['made-up']
        del data['consent']
        form = DubbingForm(data, {'video': video()})
        self.assertFalse(form.is_valid())
        self.assertIn('consent', form.errors)
        self.assertIn('target_locales', form.errors)

    @patch('studio.views.process_job.delay')
    def test_upload_enqueued_after_commit_and_idempotent(self, delay):
        token = uuid.uuid4()
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(reverse('studio:create'), self.post_data(token))
            self.assertFalse(delay.called)
        self.assertEqual(result.status_code, 302)
        delay.assert_called_once_with(str(token))
        uploaded = DubbingJob.objects.get(pk=token)
        self.assertTrue(uploaded.source.storage.exists(uploaded.source.name))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('studio:create'), self.post_data(token))
        delay.assert_called_once()
        self.assertEqual(DubbingJob.objects.filter(pk=token).count(), 1)

    @patch('studio.views.process_job.delay', side_effect=OperationalError('offline'))
    def test_broker_outage_preserves_queued_job(self, delay):
        token = uuid.uuid4()
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(reverse('studio:create'), self.post_data(token))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(DubbingJob.objects.get(pk=token).status, 'queued')

    @override_settings(STUDIO_MAX_ACTIVE_JOBS=1)
    @patch('studio.views.process_job.delay')
    def test_active_quota(self, delay):
        result = self.client.post(reverse('studio:create'), self.post_data())
        self.assertContains(result, 'Attendez la fin')
        self.assertEqual(DubbingJob.objects.count(), 1)
        delay.assert_not_called()

    def test_other_user_cannot_view_status_resume_or_download(self):
        other = DubbingJob.objects.create(user=self.other, title='Privé', original_name='private.mp4', target_locales=['en_US'])
        output = DubbingOutput.objects.create(job=other, locale='en_US', video='secret.mp4')
        for name in ('detail', 'status'):
            self.assertEqual(self.client.get(reverse(f'studio:{name}', args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('studio:resume', args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('studio:download', args=[other.pk, output.pk, 'video'])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('studio:index')), 'Privé')

    def test_unverified_and_anonymous_blocked(self):
        EmailAddress.objects.filter(user=self.user).update(verified=False)
        self.assertEqual(self.client.get(reverse('studio:index')).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('studio:index')).status_code, 302)

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('studio:create'), self.post_data()).status_code, 403)

    def test_submit_uses_jobs_only_and_duplicate_task_does_not_resubmit(self):
        client, provider = self.provider()
        with provider, patch.object(InMemoryStorage, 'url', return_value='https://source.example/signed'):
            process_job.run(str(self.job.pk))
            process_job.run(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.murf_job_id, 'murf-test')
        self.assertEqual(self.job.status, 'processing')
        client.dubbing.jobs.create.assert_called_once()
        self.assertNotIn('project_id', client.dubbing.jobs.create.call_args.kwargs)
        self.assertEqual(client.dubbing.jobs.create.call_args.kwargs['request_options']['max_retries'], 0)
        client.dubbing.projects.create.assert_not_called()

    def test_timeout_requires_review_and_no_post_retry(self):
        client, provider = self.provider(error=httpx.ReadTimeout('timeout'))
        with provider, patch.object(InMemoryStorage, 'url', return_value='https://source.example/signed'):
            process_job.run(str(self.job.pk))
            process_job.run(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'review')
        client.dubbing.jobs.create.assert_called_once()

    def test_rejection_fails_without_retry(self):
        _, provider = self.provider(error=ApiError(status_code=403))
        with provider, patch.object(InMemoryStorage, 'url', return_value='https://source.example/signed'):
            process_job.run(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'failed')

    def test_completed_results_saved_to_private_storage(self):
        self.prepare_poll()
        detail = SimpleNamespace(locale='en_US', status='COMPLETED', download_url='https://cdn.murf.ai/video.mp4', download_srt_url='https://cdn.murf.ai/video.srt')
        client, provider = self.provider(response(details=[detail]))
        def copy(url, field, name):
            if not field:
                field.save(name, ContentFile(b'output'), save=True)
        with provider, patch('studio.tasks.save_remote_file', side_effect=copy):
            process_job.run(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'completed')
        self.assertEqual(self.job.provider_credits_used, 2)
        output = self.job.outputs.get()
        self.assertTrue(output.video)
        self.assertTrue(output.subtitles)
        page = self.client.get(reverse('studio:status', args=[self.job.pk]))
        self.assertNotContains(page, 'hx-trigger="every 10s"')
        client.dubbing.jobs.create.assert_not_called()

    def test_partial_result_and_failure_message(self):
        self.prepare_poll()
        self.job.target_locales = ['en_US', 'de_DE']
        self.job.save()
        items = [SimpleNamespace(locale='en_US', status='COMPLETED', download_url='https://cdn.murf.ai/out.mp4', download_srt_url=None),
            SimpleNamespace(locale='de_DE', status='FAILED', download_url=None, download_srt_url=None)]
        _, provider = self.provider(response('PARTIALLY_COMPLETED', items))
        with provider, patch('studio.tasks.save_remote_file', side_effect=lambda url, field, name: field.save(name, ContentFile(b'output'), save=True)):
            process_job.run(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'partial')
        self.assertTrue(self.job.outputs.get(locale='de_DE').error_message)

    def test_storage_failure_retries_get_not_create(self):
        self.prepare_poll()
        detail = SimpleNamespace(locale='en_US', status='COMPLETED', download_url='https://cdn.murf.ai/out.mp4', download_srt_url=None)
        client, provider = self.provider(response(details=[detail]))
        with provider, patch('studio.tasks.save_remote_file', side_effect=OSError('storage offline')):
            process_job.run(str(self.job.pk))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'processing')
        self.assertEqual(self.job.attempts, 1)
        self.assertIsNotNone(self.job.next_check_at)
        client.dubbing.jobs.create.assert_not_called()

    @patch('studio.tasks.process_job.delay')
    def test_reconciler_recovers_queue_and_flags_ambiguous_submission(self, delay):
        self.job.status = 'submitting'
        self.job.lease_until = timezone.now() - timedelta(minutes=1)
        self.job.save()
        queued = DubbingJob.objects.create(user=self.user, title='En attente', original_name='test.mp4', target_locales=['en_US'])
        dispatch_jobs.run()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'review')
        delay.assert_called_once_with(str(queued.pk))

    @patch('studio.views.process_job.delay')
    def test_resume_only_known_job(self, delay):
        self.job.status = 'review'
        self.job.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('studio:resume', args=[self.job.pk]))
        delay.assert_not_called()
        self.job.murf_job_id = 'murf-test'
        self.job.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('studio:resume', args=[self.job.pk]))
        delay.assert_called_once()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'processing')

    def test_download_signed_after_owner_check(self):
        output = DubbingOutput.objects.create(job=self.job, locale='en_US', video='private.mp4')
        with patch.object(InMemoryStorage, 'url', return_value='https://private.example/temporary') as sign:
            result = self.client.get(reverse('studio:download', args=[self.job.pk, output.pk, 'video']))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result['Location'], 'https://private.example/temporary')
        self.assertIn('no-store', result['Cache-Control'])
        self.assertEqual(sign.call_args.kwargs['expire'], 300)
