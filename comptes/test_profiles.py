from importlib import import_module
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from .models import Profile
from .signals import create_user_profile


class ProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='profile-test', email='profile@example.test')
        EmailAddress.objects.create(user=self.user, email=self.user.email, primary=True, verified=True)
        self.url = reverse('profil_compte')

    def image_upload(self, size=(800, 600), format='PNG', name='portrait.png', padding=0):
        content = BytesIO()
        Image.new('RGB', size, '#627a42').save(content, format=format)
        return SimpleUploadedFile(name, content.getvalue() + b'0' * padding, content_type='image/png')

    def login(self):
        self.client.force_login(self.user)

    def test_signal_creates_one_profile_and_preserves_it_on_user_update(self):
        profile = self.user.profile
        profile.bio = 'Créatrice de vidéos.'
        profile.save()
        self.user.first_name = 'Awa'
        self.user.save()
        create_user_profile(get_user_model(), self.user, True, False, 'default')
        profile.refresh_from_db()
        self.assertEqual(Profile.objects.filter(user=self.user).count(), 1)
        self.assertEqual(profile.bio, 'Créatrice de vidéos.')

    def test_raw_fixture_save_skips_profile_creation(self):
        self.user.profile.delete()
        create_user_profile(get_user_model(), self.user, True, True, 'default')
        self.assertFalse(Profile.objects.filter(user=self.user).exists())

    def test_google_social_account_save_creates_profile(self):
        user = get_user_model()(username='google-profile', email='google-profile@example.test', first_name='Awa')
        user.set_unusable_password()
        sociallogin = SocialLogin(
            user=user, account=SocialAccount(provider='google', uid='google-profile-test'),
            email_addresses=[EmailAddress(email=user.email, primary=True, verified=True)],
        )
        request = RequestFactory().get('/comptes/google/login/callback/')
        request.session = {}
        sociallogin.save(request)
        self.assertEqual(user.profile.user_id, user.pk)
        self.assertEqual(user.first_name, 'Awa')
        sociallogin.save(request, connect=True)
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_backfill_creates_missing_profiles_without_changing_existing(self):
        self.user.profile.delete()
        other = get_user_model().objects.create_user(username='other-profile')
        other.profile.bio = 'À conserver.'
        other.profile.save()
        backfill = import_module('comptes.migrations.0002_profiles_for_existing_users').create_existing_profiles
        editor = SimpleNamespace(connection=connection)
        backfill(apps, editor)
        backfill(apps, editor)
        self.assertEqual(Profile.objects.count(), 2)
        other.profile.refresh_from_db()
        self.assertEqual(other.profile.bio, 'À conserver.')

    def test_profile_requires_login_and_verified_email(self):
        self.assertRedirects(self.client.get(self.url), reverse('account_login') + '?next=' + self.url)
        self.login()
        EmailAddress.objects.filter(user=self.user).update(verified=False)
        response = self.client.post(self.url, {'first_name': 'Refusé'})
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')

    def test_profile_page_and_htmx_update_only_current_user(self):
        other = get_user_model().objects.create_user(username='other-user')
        self.login()
        page = self.client.get(self.url)
        self.assertContains(page, 'Mon profil')
        self.assertIn('no-store', page['Cache-Control'])
        self.assertIn('HX-Request', page['Vary'])
        response = self.client.post(self.url, {
            'first_name': 'Awa', 'last_name': 'Koné', 'bio': 'Mes vidéos.',
            'user': other.pk, 'email': 'changed@example.test',
        }, HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Votre profil a été mis à jour.')
        self.assertNotContains(response, '<!DOCTYPE')
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.user.get_full_name(), 'Awa Koné')
        self.assertEqual(self.user.email, 'profile@example.test')
        self.assertEqual(self.user.profile.bio, 'Mes vidéos.')
        self.assertEqual(other.first_name, '')

    def test_standard_post_redirects_and_csrf_is_required(self):
        self.login()
        self.assertRedirects(self.client.post(self.url, {'first_name': 'Awa'}), self.url + '?saved=1')
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {}).status_code, 403)

    def test_upload_resizes_photo_and_scopes_its_storage_path(self):
        self.login()
        upload = self.image_upload(padding=6 * 1024 * 1024)
        self.assertGreater(upload.size, 5 * 1024 * 1024)
        self.client.post(self.url, {'avatar': upload})
        profile = Profile.objects.get(user=self.user)
        self.assertTrue(profile.avatar.name.startswith(f'profiles/{self.user.pk}/'))
        self.assertNotIn('portrait', profile.avatar.name)
        with profile.avatar.open('rb') as photo:
            self.assertEqual(Image.open(photo).size, (512, 384))
        self.assertContains(self.client.get(self.url), 'Votre photo de profil')

    def test_invalid_images_and_excessive_dimensions_do_not_change_profile(self):
        self.login()
        files = (
            SimpleUploadedFile('fake.png', b'not an image', content_type='image/png'),
            self.image_upload(format='GIF', name='photo.gif'),
            self.image_upload(size=(4097, 1)),
        )
        for upload in files:
            with self.subTest(upload=upload.name):
                response = self.client.post(self.url, {'first_name': 'Refusé', 'avatar': upload}, HTTP_HX_REQUEST='true')
                self.assertTrue(response.context['form'].errors.get('avatar'))
                self.user.refresh_from_db()
                self.assertEqual(self.user.first_name, '')
                self.assertFalse(self.user.profile.avatar)

    def test_storage_failure_rolls_back_name_and_photo(self):
        self.login()
        storage = Profile._meta.get_field('avatar').storage
        with patch.object(storage, 'save', side_effect=OSError('Storage unavailable')):
            response = self.client.post(self.url, {'first_name': 'Refusé', 'avatar': self.image_upload()}, HTTP_HX_REQUEST='true')
        self.assertContains(response, 'La photo n’a pas pu être enregistrée.')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')
        self.assertFalse(self.user.profile.avatar)

    def test_replacing_and_removing_photo_deletes_old_file_after_commit(self):
        self.login()
        self.client.post(self.url, {'avatar': self.image_upload()})
        old = Profile.objects.get(user=self.user).avatar
        old_name = old.name
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {'avatar': self.image_upload()})
        self.assertFalse(old.storage.exists(old_name))
        current = Profile.objects.get(user=self.user).avatar
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {'avatar-clear': 'on'})
        self.assertFalse(current.storage.exists(current.name))
        self.assertFalse(Profile.objects.get(user=self.user).avatar)

    def test_user_deletion_removes_profile_and_photo(self):
        self.login()
        self.client.post(self.url, {'avatar': self.image_upload()})
        avatar = Profile.objects.get(user=self.user).avatar
        with self.captureOnCommitCallbacks(execute=True):
            self.user.delete()
        self.assertFalse(Profile.objects.exists())
        self.assertFalse(avatar.storage.exists(avatar.name))
