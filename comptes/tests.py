from urllib.parse import parse_qs, urlparse
import re
from smtplib import SMTPServerDisconnected
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from .models import Profile


@override_settings(ACCOUNT_RATE_LIMITS={})
class AuthenticationTests(TestCase):
    password = 'Canvas!Orbit72River'
    email = 'demo@example.test'

    def setUp(self):
        cache.clear()

    def signup(self, **changes):
        data = {'email': self.email, 'password1': self.password, 'password2': self.password}
        data.update(changes)
        return self.client.post(reverse('account_signup'), data, HTTP_HX_REQUEST='true')

    def create_user(self):
        user = get_user_model().objects.create_user(username='demo', email=self.email, password=self.password)
        EmailAddress.objects.create(user=user, email=self.email, primary=True, verified=True)
        return user

    def test_signup_and_htmx_redirect(self):
        response = self.signup()
        self.assertEqual(response['HX-Redirect'], reverse('account_email_verification_sent'))
        user = get_user_model().objects.get(email=self.email)
        self.assertEqual(user.profile.user_id, user.pk)
        self.assertTrue(user.check_password(self.password))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFalse(EmailAddress.objects.get(user=user).verified)
        self.assertEqual(len(mail.outbox), 1)

    @patch('django.core.mail.backends.locmem.EmailBackend.send_messages', side_effect=SMTPServerDisconnected('SMTP unavailable'))
    def test_mandatory_confirmation_failure_does_not_create_partial_account(self, send_messages):
        response = self.signup()
        self.assertContains(response, 'Le service d’email est momentanément indisponible')
        self.assertNotIn('HX-Redirect', response)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Profile.objects.exists())
        self.assertNotIn('_auth_user_id', self.client.session)

    @patch('django.core.mail.backends.locmem.EmailBackend.send_messages', side_effect=SMTPServerDisconnected('SMTP unavailable'))
    def test_password_reset_smtp_failure_returns_error_fragment(self, send_messages):
        self.create_user()
        response = self.client.post(reverse('account_reset_password'), {'email': self.email}, HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Le service d’email est momentanément indisponible')
        self.assertNotContains(response, '<!DOCTYPE')
        self.assertNotIn('HX-Redirect', response)

    @patch('django.core.mail.backends.locmem.EmailBackend.send_messages', side_effect=SMTPServerDisconnected('SMTP unavailable'))
    def test_unverified_email_login_blocked_when_confirmation_send_fails(self, send_messages):
        user = self.create_user()
        address = EmailAddress.objects.get(user=user)
        address.verified = False
        address.save()
        response = self.client.post(reverse('account_login'), {'login': self.email, 'password': self.password}, HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Le service d’email est momentanément indisponible')
        self.assertNotIn('HX-Redirect', response)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signup_confirmation_resumes_login_then_opens_space(self):
        self.signup()
        address = EmailAddress.objects.get(email=self.email)
        url = reverse('account_confirm_email', args=[EmailConfirmationHMAC(address).key])
        self.client.get(url)
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(url)
        self.assertRedirects(response, reverse('espace_compte'))
        address.refresh_from_db()
        self.assertTrue(address.verified)
        self.assertEqual(int(self.client.session['_auth_user_id']), address.user_id)

    def test_existing_unverified_session_cannot_open_space(self):
        user = self.create_user()
        EmailAddress.objects.filter(user=user).update(verified=False)
        self.client.force_login(user)
        response = self.client.get(reverse('espace_compte'))
        self.assertContains(response, 'Confirmez votre adresse email.', status_code=403)
        self.assertNotContains(response, 'Votre studio prend forme.', status_code=403)
        self.assertEqual(len(mail.outbox), 0)

    def test_unverified_login_waits_for_confirmation(self):
        user = self.create_user()
        EmailAddress.objects.filter(user=user).update(verified=False)
        response = self.client.post(reverse('account_login'), {'login': self.email, 'password': self.password}, HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], reverse('account_email_verification_sent'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_mismatch_fragment(self):
        response = self.signup(password2='Another!Secret98')
        self.assertContains(response, 'id="auth-card"')
        self.assertNotContains(response, '<!DOCTYPE')
        self.assertTrue(response.context['form'].errors.get('password2'))
        self.assertFalse(get_user_model().objects.exists())

    def test_weak_password(self):
        response = self.signup(password1='123', password2='123')
        self.assertTrue(response.context['form'].errors.get('password1'))
        self.assertFalse(get_user_model().objects.exists())

    def test_duplicate_email_case_insensitive(self):
        self.create_user()
        self.signup(email='DEMO@example.test')
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_email_login_and_bad_password(self):
        user = self.create_user()
        invalid = self.client.post(reverse('account_login'), {'login': self.email, 'password': 'Wrong!Secret99'}, HTTP_HX_REQUEST='true')
        self.assertTrue(invalid.context['form'].non_field_errors())
        self.assertNotIn('_auth_user_id', self.client.session)
        valid = self.client.post(reverse('account_login'), {'login': self.email, 'password': self.password}, HTTP_HX_REQUEST='true')
        self.assertEqual(valid['HX-Redirect'], reverse('espace_compte'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_external_next_rejected(self):
        self.create_user()
        response = self.client.post(reverse('account_login'), {'login': self.email, 'password': self.password, 'next': 'https://evil.example/'})
        self.assertRedirects(response, reverse('espace_compte'))

    def test_protected_space_and_logout(self):
        self.assertRedirects(self.client.get(reverse('espace_compte')), reverse('account_login') + '?next=' + reverse('espace_compte'))
        self.client.force_login(self.create_user())
        self.assertEqual(self.client.get(reverse('espace_compte')).status_code, 200)
        self.client.get(reverse('account_logout'))
        self.assertIn('_auth_user_id', self.client.session)
        self.client.post(reverse('account_logout'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_message_is_consumed_before_next_login(self):
        self.client.force_login(self.create_user())
        logout = self.client.post(reverse('account_logout'), follow=True)
        self.assertContains(logout, 'déconnecté')
        login = self.client.post(reverse('account_login'), {'login': self.email, 'password': self.password}, follow=True)
        self.assertContains(login, 'Bienvenue sur Dublao. Vous êtes connecté(e).')
        self.assertNotContains(login, 'déconnecté')
        self.assertNotContains(login, 'Connexion avec demo')

    def test_csrf(self):
        client = Client(enforce_csrf_checks=True)
        for name in ('account_signup', 'account_login', 'account_logout', 'google_login'):
            self.assertEqual(client.post(reverse(name), {}).status_code, 403)

    def test_reset_email(self):
        self.create_user()
        response = self.client.post(reverse('account_reset_password'), {'email': self.email}, HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], reverse('account_reset_password_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/comptes/password/reset/key/', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].subject, '[Dublao] Réinitialisez votre mot de passe')
        self.assertEqual(mail.outbox[0].to, [self.email])
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, 'text/html')
        missing = self.client.post(reverse('account_reset_password'), {'email': 'missing@example.test'}, HTTP_HX_REQUEST='true')
        self.assertEqual(missing['HX-Redirect'], response['HX-Redirect'])

    def test_pages_no_cache(self):
        for name in ('account_signup', 'account_login', 'account_reset_password'):
            response = self.client.get(reverse(name))
            self.assertContains(response, '<!DOCTYPE')
            self.assertIn('no-store', response['Cache-Control'])
            self.assertIn('HX-Request', response['Vary'])

    def test_reset_token_changes_password_and_cannot_be_reused(self):
        user = self.create_user()
        self.client.post(reverse('account_reset_password'), {'email': self.email})
        link = re.search(r'https?://[^\s]+/comptes/password/reset/key/[^\s]+', mail.outbox[0].body).group()
        path = urlparse(link).path
        page = self.client.get(path, follow=True)
        action = page.context['action_url']
        response = self.client.post(action, {'password1': 'New!Canvas89River', 'password2': 'New!Canvas89River'}, follow=True)
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password('New!Canvas89River'))
        self.assertFalse(user.check_password(self.password))
        self.client.logout()
        expired = self.client.get(path, follow=True)
        self.assertContains(expired, 'Ce lien est invalide ou a expiré.')

    def test_retired_email_page_redirects_without_sending(self):
        self.client.force_login(self.create_user())
        self.assertRedirects(self.client.get(reverse('account_email')), reverse('espace_compte'))
        self.client.post(reverse('account_email'), {'email': self.email, 'action_send': '1'})
        self.assertEqual(len(mail.outbox), 0)

    def test_confirmation_requires_post_and_confirms_address(self):
        user = self.create_user()
        address = EmailAddress.objects.get(user=user)
        address.verified = False
        address.save()
        key = EmailConfirmationHMAC(address).key
        url = reverse('account_confirm_email', args=[key])
        self.assertContains(self.client.get(url), 'Confirmer mon adresse')
        address.refresh_from_db()
        self.assertFalse(address.verified)
        self.client.post(url)
        address.refresh_from_db()
        self.assertTrue(address.verified)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signup_confirmation_email_uses_dublao_html(self):
        self.signup()
        self.assertEqual(mail.outbox[0].subject, '[Dublao] Bienvenue sur Dublao : confirmez votre email')
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, 'text/html')
        self.assertIn('Confirmer mon adresse email', mail.outbox[0].alternatives[0].content)

    @override_settings(GOOGLE_OAUTH_ENABLED=True, SOCIALACCOUNT_PROVIDERS={'google': {
        'APP': {'client_id': 'test.apps.googleusercontent.com', 'secret': 'test-secret', 'key': ''},
        'SCOPE': ['profile', 'email'],
    }})
    def test_google_oauth_state_and_callback(self):
        response = self.client.post(reverse('google_login'))
        self.assertEqual(response.status_code, 302)
        location = urlparse(response['Location'])
        self.assertEqual(location.hostname, 'accounts.google.com')
        query = parse_qs(location.query)
        self.assertTrue(query['state'][0])
        self.assertEqual(query['redirect_uri'], ['http://testserver/comptes/google/login/callback/'])
        self.assertContains(self.client.get(reverse('account_login')), 'action="/comptes/google/login/"')
        self.assertEqual(self.client.get(reverse('google_login')).status_code, 200)
