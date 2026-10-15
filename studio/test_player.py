from unittest.mock import patch
from html.parser import HTMLParser

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.files.storage import InMemoryStorage
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import DubbingJob, DubbingLanguage, DubbingOutput


class SelectedLanguages(HTMLParser):
    def __init__(self, html, name='target_locales'):
        super().__init__()
        self.values = []
        self.name = name
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name') == self.name and 'checked' in attrs:
            self.values.append(attrs['value'])


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StudioPlayerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='viewer', email='viewer@example.com')
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True)
        self.client.force_login(self.user)
        self.job = DubbingJob.objects.create(user=self.user, title='Tutoriel doublé',
            target_locales=['en_US'], status='completed')
        self.output = DubbingOutput.objects.create(job=self.job, locale='en_US',
            video='private/result.mp4', subtitles='private/result.srt')

    def watch_url(self, job=None, output=None):
        return reverse('studio:watch', args=[(job or self.job).pk, (output or self.output).pk])

    def test_watch_signs_inline_after_authorization_and_never_caches(self):
        with patch.object(InMemoryStorage, 'url', return_value='https://private.example/signed') as sign:
            result = self.client.get(self.watch_url())
        self.assertEqual(result.status_code, 302)
        sign.assert_called_once_with('private/result.mp4', expire=3600, parameters={
            'ResponseContentDisposition': 'inline', 'ResponseContentType': 'video/mp4'})
        self.assertIn('no-store', result['Cache-Control'])
        self.assertEqual(result['Referrer-Policy'], 'no-referrer')

    def test_watch_refuses_other_owner_and_output_from_another_job(self):
        other = get_user_model().objects.create_user(username='another')
        private = DubbingJob.objects.create(user=other, title='Privé')
        private_output = DubbingOutput.objects.create(job=private, locale='en_US', video='secret.mp4')
        with patch.object(InMemoryStorage, 'url') as sign:
            self.assertEqual(self.client.get(self.watch_url(private, private_output)).status_code, 404)
            self.assertEqual(self.client.get(self.watch_url(self.job, private_output)).status_code, 404)
            sign.assert_not_called()

    def test_watch_requires_verified_account(self):
        EmailAddress.objects.filter(user=self.user).update(verified=False)
        with patch.object(InMemoryStorage, 'url') as sign:
            self.assertEqual(self.client.get(self.watch_url()).status_code, 403)
            sign.assert_not_called()
        self.client.logout()
        self.assertEqual(self.client.get(self.watch_url()).status_code, 302)

    def test_archive_remains_downloadable_without_broken_player(self):
        self.output.video = 'private/result.zip'
        self.output.save()
        self.assertEqual(self.client.get(self.watch_url()).status_code, 404)
        page = self.client.get(reverse('studio:detail', args=[self.job.pk]))
        self.assertNotContains(page, '<video ')
        self.assertContains(page, 'Ce format est disponible au téléchargement.')
        self.assertContains(page, reverse('studio:download', args=[self.job.pk, self.output.pk, 'video']))

    def test_players_and_downloads_appear_in_studio_and_detail(self):
        for name, args in [('index', []), ('detail', [self.job.pk]), ('status', [self.job.pk])]:
            page = self.client.get(reverse(f'studio:{name}', args=args))
            self.assertContains(page, '<video controls playsinline')
            self.assertContains(page, self.watch_url())
            self.assertContains(page, 'Anglais · États-Unis')
            self.assertContains(page, reverse('studio:download', args=[self.job.pk, self.output.pk, 'video']))
            self.assertContains(page, reverse('studio:download', args=[self.job.pk, self.output.pk, 'subtitles']))
            self.assertNotContains(page, 'private/result.mp4')

    def test_multiple_language_buttons_keep_selection_after_form_error(self):
        DubbingLanguage.objects.create(locale='en_SCOTT', name='Scottish', source=True, target=True)
        page = self.client.post(reverse('studio:create'), {'target_locales': ['en_US', 'en_SCOTT']})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'studio/flags/us.svg')
        self.assertContains(page, 'studio/flags/gb-sct.svg')
        self.assertContains(page, 'Anglais · Écosse')
        self.assertEqual(set(SelectedLanguages(page.content.decode()).values), {'en_US', 'en_SCOTT'})
        self.assertIn('video', page.context['form'].errors)

    def test_source_only_languages_have_flags_without_becoming_invalid_targets(self):
        DubbingLanguage.objects.create(locale='uk_UA', name='Ukrainian', source=True, target=False)
        DubbingLanguage.objects.create(locale='no_NO', name='Norwegian', source=True, target=False)
        DubbingLanguage.objects.create(locale='nb_NO', name='Bokmal', source=False, target=True)
        page = self.client.post(reverse('studio:create'), {'source_locale': 'no_NO', 'target_locales': ['en_US']})
        self.assertContains(page, 'Ukrainien')
        self.assertContains(page, 'studio/flags/ua.svg')
        self.assertEqual(SelectedLanguages(page.content.decode(), 'source_locale').values, ['no_NO'])
        targets = dict(page.context['form'].fields['target_locales'].choices)
        self.assertIn('nb_NO', targets)
        self.assertNotIn('no_NO', targets)
        self.assertNotIn('uk_UA', targets)
