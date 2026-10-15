import json
import re
from xml.etree import ElementTree

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from .seo import public_origin


@override_settings(DEBUG=False, SITE_PUBLIC_URL='https://dublao.example', SEO_INDEXING_ENABLED=True)
class PublicSearchTests(TestCase):
    def test_language_urls_are_stable_despite_cookie_and_accept_language(self):
        for language, cookie, title in [('en', 'fr', 'AI video dubbing in 44 languages'),
                                        ('fr', 'en', 'Doublage vidéo IA dans 44 langues')]:
            self.client.cookies['django_language'] = cookie
            response = self.client.get(f'/{language}/', HTTP_ACCEPT_LANGUAGE=cookie)
            self.assertContains(response, f'<html lang="{language}">')
            self.assertContains(response, title)
            self.assertEqual(response['Content-Language'], language)
            self.assertContains(response, f'rel="canonical" href="https://dublao.example/{language}/"')
            self.assertContains(response, 'hreflang="fr"')
            self.assertContains(response, 'hreflang="en"')
            self.assertContains(response, 'name="next" value="/"')

    def test_sitemap_contains_only_public_canonical_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        document = ElementTree.fromstring(response.content)
        locations = [node.text for node in document.findall('{*}url/{*}loc')]
        self.assertEqual(locations, ['https://dublao.example/fr/', 'https://dublao.example/en/'])
        self.assertNotContains(response, '/credits/')

    def test_private_pages_are_noindex_and_robots_points_to_sitemap(self):
        response = self.client.get('/comptes/signup/')
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
        self.assertContains(response, 'content="noindex, nofollow"')
        self.assertNotContains(response, 'rel="canonical"')
        robots = self.client.get('/robots.txt')
        self.assertContains(robots, 'Sitemap: https://dublao.example/sitemap.xml')
        self.assertContains(robots, 'Disallow: /studio/')

    def test_authenticated_homepage_is_not_indexable(self):
        user = get_user_model().objects.create_user(username='seo-private', email='seo@example.test')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/')['X-Robots-Tag'], 'noindex, nofollow')

    def test_structured_data_uses_public_origin_without_user_or_query_data(self):
        response = self.client.get('/en/?private=do-not-publish')
        content = response.content.decode()
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', content).group(1))
        self.assertEqual(data['@graph'][0]['name'], 'Dublao')
        self.assertEqual(data['@graph'][0]['url'], 'https://dublao.example/')
        self.assertNotIn('do-not-publish', data.__str__())

    @override_settings(SITE_PUBLIC_URL='', SEO_INDEXING_ENABLED=True)
    def test_no_domain_keeps_site_out_of_index(self):
        self.assertContains(self.client.get('/robots.txt'), 'Disallow: /')
        self.assertEqual(self.client.get('/sitemap.xml').status_code, 404)
        self.assertEqual(self.client.get('/')['X-Robots-Tag'], 'noindex, nofollow')

    @override_settings(DEBUG=True)
    def test_debug_site_cannot_enable_indexing(self):
        self.assertContains(self.client.get('/robots.txt'), 'Disallow: /')
        self.assertEqual(self.client.get('/')['X-Robots-Tag'], 'noindex, nofollow')

    def test_unsafe_origins_are_rejected(self):
        for value in ['http://dublao.example', 'https://localhost', 'https://127.0.0.1',
                      'https://user:secret@dublao.example', 'https://dublao.example/credits/',
                      'https://dublao.example?secret=value']:
            with self.subTest(value=value), override_settings(SITE_PUBLIC_URL=value):
                with self.assertRaises(ImproperlyConfigured):
                    public_origin()
