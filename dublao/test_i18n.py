from django.test import TestCase, Client
from django.urls import reverse
from django.utils.translation import override
from django.template.loader import render_to_string
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from studio.models import DubbingJob
from studio.languages import language_name


class InterfaceLanguageTests(TestCase):
    def test_switch_persists_on_same_page_and_changes_html_language(self):
        client = Client()
        response = client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        self.assertRedirects(response, '/')
        self.assertEqual(response.cookies['django_language'].value, 'en')
        page = client.get('/')
        self.assertContains(page, '<html lang="en">')
        self.assertContains(page, 'Get started')
        self.assertContains(page, 'Your voice stays yours')
        self.assertContains(page, 'data-language-selector')
        self.assertContains(page, 'In 44 languages.')
        self.assertNotContains(page, 'interface-settings')
        self.assertNotContains(page, '>Apply<')
        self.assertNotContains(page, '>Commencer<')
        client.post(reverse('set_language'), {'language': 'fr', 'next': '/'})
        self.assertContains(client.get('/'), '<html lang="fr">')
        self.assertContains(client.get('/'), 'Votre voix reste la vôtre')

    def test_language_switch_is_csrf_protected_and_rejects_external_redirect(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse('set_language'), {'language': 'en'}).status_code, 403)
        response = self.client.post(reverse('set_language'), {'language': 'en', 'next': 'https://untrusted.example/'})
        self.assertEqual(response['Location'], '/')

    def test_protected_pages_render_in_english(self):
        user = get_user_model().objects.create_user(username='language-check', email='language@example.test', is_staff=True)
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        self.client.force_login(user)
        self.client.cookies['django_language'] = 'en'
        for view, label in [('studio:index', 'My dubbed videos'), ('studio:create', 'Dubbing settings'),
                            ('credits:wallet', 'Choose your pack'), ('profil_compte', 'Save my profile'),
                            ('espace_compte', 'My workspace'), ('supervision:dashboard', 'Visitors')]:
            with self.subTest(view=view):
                response = self.client.get(reverse(view))
                self.assertContains(response, label)
                if view == 'credits:wallet':
                    self.assertContains(response, 'Continue to payment')
                    self.assertNotContains(response, 'Pay with Genius Pay')

    def test_status_and_language_names_keep_machine_codes(self):
        with override('en'):
            job = DubbingJob(status='completed')
            self.assertEqual(job.get_status_display(), 'Completed')
            self.assertEqual(job.status, 'completed')
            self.assertEqual(str(language_name('ko_KR')), 'Korean')
        with override('fr'):
            self.assertEqual(str(language_name('ko_KR')), 'Coréen')

    def test_email_and_javascript_catalog_are_translated(self):
        with override('en'):
            email = render_to_string('account/email/email_confirmation_message.txt', {'activate_url': 'https://example.test/confirm/'})
            self.assertIn('Confirm your email address', email)
            self.assertIn('https://example.test/confirm/', email)
        self.client.cookies['django_language'] = 'en'
        catalog = self.client.get(reverse('javascript-catalog'))
        self.assertContains(catalog, 'A new dubbed version is available.')
