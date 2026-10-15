from django.test import SimpleTestCase, RequestFactory, override_settings
from django.utils.translation import override
from django.http import Http404
from django.urls import path, include
from django.core.exceptions import PermissionDenied, SuspiciousOperation

from . import errors
from .middleware import FriendlyNotFoundMiddleware
from django.http import JsonResponse


def missing(request):
    raise Http404('private-token-secret')


def forbidden(request):
    raise PermissionDenied('private-token-secret')


def bad(request):
    raise SuspiciousOperation('private-token-secret')


def broken(request):
    raise RuntimeError('private-token-secret')


urlpatterns = [path('missing/', missing), path('forbidden/', forbidden), path('bad/', bad), path('broken/', broken), path('', include('dublao.urls'))]
handler400 = errors.bad_request
handler403 = errors.permission_denied
handler404 = errors.page_not_found
handler500 = errors.server_error


class ErrorScreenTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF=__name__)
    def test_unknown_urls_show_friendly_page_in_both_modes(self):
        for debug in (True, False):
            for language in ('fr', 'en'):
                with self.subTest(debug=debug, language=language), override_settings(DEBUG=debug):
                    response = self.client.get('/unknown-private-token-secret/', HTTP_ACCEPT_LANGUAGE=language)
                    self.assertContains(response, 'error-title', status_code=404)
                    self.assertContains(response, f'<html lang="{language}">', status_code=404)
                    self.assertNotContains(response, 'unknown-private-token-secret', status_code=404)
                    self.assertNotContains(response, 'URLconf', status_code=404)
                    self.assertEqual(response['Cache-Control'], 'no-store')

    @override_settings(DEBUG=True)
    def test_json_not_found_is_preserved(self):
        original = JsonResponse({'error': 'not_found'}, status=404)
        response = FriendlyNotFoundMiddleware(lambda request: original)(RequestFactory().get('/api/missing/'))
        self.assertIs(response, original)
        self.assertEqual(response.content, b'{"error": "not_found"}')

    def test_all_pages_render_without_database_and_keep_status(self):
        for language in ('fr', 'en'):
            with override(language):
                for code in errors.ERRORS:
                    with self.subTest(language=language, code=code):
                        response = errors.error_response(code)
                        self.assertEqual(response.status_code, code)
                        self.assertEqual(response['Cache-Control'], 'no-store')
                        self.assertContains(response, f'<html lang="{language}">', status_code=code)
                        self.assertContains(response, 'error-title', status_code=code)
                        self.assertNotContains(response, '<script', status_code=code)

    @override_settings(DEBUG=False, ROOT_URLCONF=__name__)
    def test_real_exceptions_use_custom_handlers_without_exposing_details(self):
        self.client.raise_request_exception = False
        for url, code in [('/missing/', 404), ('/forbidden/', 403), ('/bad/', 400), ('/broken/', 500)]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'Dublao', status_code=code)
                self.assertNotContains(response, 'private-token-secret', status_code=code)

    def test_csrf_failure_does_not_display_reason(self):
        response = errors.csrf_failure(RequestFactory().post('/credits/acheter/'), reason='private-token-secret')
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, 'private-token-secret', status_code=403)
