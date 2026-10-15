from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.files.storage import InMemoryStorage
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import DubbingJob, DubbingLanguage, DubbingOutput
from .presentation import studio_config


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StudioEditorTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='editor', email='editor@example.test')
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True)
        self.client.force_login(self.user)
        self.job = DubbingJob.objects.create(user=self.user, title='Projet studio',
            source='private/source.mp4', original_name='source.mp4', duration_ms=61000,
            target_locales=['en_US', 'fr_FR'], status='processing', murf_job_id='private-provider-id')

    def test_studio_root_opens_editor_and_projects_remain_separate(self):
        self.assertEqual(reverse('studio:create'), '/studio/')
        page = self.client.get('/studio/')
        self.assertContains(page, 'studio-config')
        self.assertContains(page, 'action="/studio/"')
        self.assertNotContains(page, 'Nouveau doublage')
        self.assertEqual(reverse('studio:index'), '/studio/projets/')
        self.assertContains(self.client.get('/studio/projets/'), 'Projet studio')

    def test_legacy_editor_redirects_get_but_keeps_old_form_submissions(self):
        self.assertRedirects(self.client.get('/studio/nouveau/'), '/studio/')
        response = self.client.post('/studio/nouveau/', {'title': 'Conserver ma saisie'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Conserver ma saisie')
        self.assertIn('video', response.context['form'].errors)

    def test_original_is_signed_only_after_owner_and_verification_checks(self):
        url = reverse('studio:original', args=[self.job.pk])
        with patch.object(InMemoryStorage, 'url', return_value='https://private.example/signed') as sign:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        sign.assert_called_once_with('private/source.mp4', expire=3600, parameters={
            'ResponseContentDisposition': 'inline', 'ResponseContentType': 'video/mp4'})
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        other = get_user_model().objects.create_user(username='private-owner')
        self.job.user = other
        self.job.save()
        with patch.object(InMemoryStorage, 'url') as sign:
            self.assertEqual(self.client.get(url).status_code, 404)
            sign.assert_not_called()
        self.job.user = self.user
        self.job.save()
        EmailAddress.objects.filter(user=self.user).update(verified=False)
        with patch.object(InMemoryStorage, 'url') as sign:
            self.assertEqual(self.client.get(url).status_code, 403)
            sign.assert_not_called()

    def test_versions_become_ready_only_when_their_own_file_exists(self):
        DubbingOutput.objects.create(job=self.job, locale='en_US', video='private/en.mp4')
        config = studio_config(self.user, self.job)
        self.assertEqual([v['state'] for v in config['versions']], ['ready', 'processing'])
        self.assertTrue(config['versions'][0]['downloadUrl'])
        self.assertFalse(config['versions'][1]['downloadUrl'])
        self.job.status = 'partial'
        self.job.save()
        self.assertEqual([v['state'] for v in studio_config(self.user, self.job)['versions']], ['ready', 'failed'])

    def test_polling_returns_state_fragment_without_replacing_player_or_leaking_storage(self):
        url = reverse('studio:status', args=[self.job.pk])
        response = self.client.get(url, {'view': 'studio'})
        self.assertContains(response, 'studio-state-data')
        self.assertContains(response, 'every 10s')
        self.assertNotContains(response, '<video ')
        self.assertNotContains(response, 'private/source.mp4')
        self.assertNotContains(response, 'private-provider-id')
        self.assertNotContains(response, 'progressPercent')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotContains(self.client.get(url), 'studio-state-data')
        self.job.status = 'completed'
        self.job.save()
        self.assertNotContains(self.client.get(url, {'view': 'studio'}), 'every 10s')

    def test_active_unplayable_original_retains_player_for_future_outputs(self):
        self.job.source = 'private/source.mkv'
        self.job.save()
        page = self.client.get(reverse('studio:detail', args=[self.job.pk]))
        self.assertContains(page, '<video controls playsinline')
        self.assertEqual(page.context['editor_config']['originalUrl'], '')
        with patch.object(InMemoryStorage, 'url') as sign:
            self.assertEqual(self.client.get(reverse('studio:original', args=[self.job.pk])).status_code, 404)
            sign.assert_not_called()

    def test_retry_is_exposed_only_for_existing_safe_backend_paths(self):
        self.assertFalse(studio_config(self.user, self.job)['resumeUrl'])
        self.job.status = 'review'
        self.assertTrue(studio_config(self.user, self.job)['resumeUrl'])
        self.job.status = 'failed'
        self.job.murf_job_id = ''
        self.job.error_code = 'INSUFFICIENT_USER_CREDITS'
        self.assertTrue(studio_config(self.user, self.job)['resumeUrl'])
        self.job.error_code = 'PROVIDER_ERROR'
        self.assertFalse(studio_config(self.user, self.job)['resumeUrl'])

    def test_advertised_language_count_matches_configured_targets(self):
        count = DubbingLanguage.objects.filter(target=True).count()
        for name in ('landing:home', 'studio:index', 'studio:create'):
            page = self.client.get(reverse(name))
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.context['target_language_count'], count)
        DubbingLanguage.objects.create(locale='test_XX', name='Source only', source=True, target=False)
        self.assertEqual(self.client.get(reverse('landing:home')).context['target_language_count'], count)
