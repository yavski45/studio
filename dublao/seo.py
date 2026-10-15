"""Public search metadata, independent of payment URLs and user data."""
import ipaddress
import json
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import URLValidator
from django.http import HttpResponse
from django.views.decorators.http import require_GET


PUBLIC_VIEWS = {'landing:home', 'landing:localized_home'}


def public_origin():
    value = settings.SITE_PUBLIC_URL.strip().rstrip('/')
    if not value:
        return ''
    try:
        URLValidator(schemes=['https'])(value)
        parts = urlsplit(value)
        host = parts.hostname.lower()
        if parts.username or parts.password or parts.path or parts.query or parts.fragment or parts.port not in (None, 443):
            raise ValueError
        if host == 'localhost' or host.endswith(('.localhost', '.local')):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
        return 'https://' + host.encode('idna').decode('ascii')
    except (ValidationError, ValueError, AttributeError, UnicodeError):
        raise ImproperlyConfigured('SITE_PUBLIC_URL doit être un domaine HTTPS public, sans chemin ni paramètres.') from None


def indexing_enabled():
    if settings.DEBUG or not settings.SEO_INDEXING_ENABLED:
        return False
    return bool(public_origin())


def context(request):
    return {'seo': {'robots': 'noindex, nofollow', 'enabled': False}}


def homepage_metadata(language, count):
    language = 'en' if language == 'en' else 'fr'
    texts = {
        'fr': (f'Dublao — Doublage vidéo IA dans {count} langues',
               f'Doublez vos vidéos dans {count} langues en conservant la voix originale. Pour les créateurs, les formations e-learning et les entreprises. Crédits sans abonnement.'),
        'en': (f'Dublao — AI video dubbing in {count} languages',
               f'Dub your videos into {count} languages while preserving the original voice. For creators, e-learning courses and businesses. Credits without a subscription.'),
    }
    title, description = texts[language]
    enabled = indexing_enabled()
    seo = {'title': title, 'description': description, 'enabled': enabled,
           'robots': 'index, follow' if enabled else 'noindex, nofollow'}
    if not enabled:
        return seo
    origin = public_origin()
    canonical = f'{origin}/{language}/'
    logo = origin + '/static/landing/images/dublao-logo-green.png'
    seo.update(canonical=canonical, french_url=origin+'/fr/', english_url=origin+'/en/',
               default_url=origin+'/', image=logo, locale='en_US' if language == 'en' else 'fr_FR',
               other_locale='fr_FR' if language == 'en' else 'en_US')
    seo['structured_data'] = json.dumps({
        '@context': 'https://schema.org', '@graph': [
            {'@type': 'Organization', '@id': origin+'/#organization', 'name': 'Dublao', 'url': origin+'/', 'logo': logo},
            {'@type': 'WebSite', '@id': origin+'/#website', 'name': 'Dublao', 'url': origin+'/',
             'inLanguage': ['fr', 'en'], 'publisher': {'@id': origin+'/#organization'}},
        ]}, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return seo


class IndexingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        view = getattr(getattr(request, 'resolver_match', None), 'view_name', '')
        is_public = (view in PUBLIC_VIEWS and response.status_code == 200
                     and not getattr(getattr(request, 'user', None), 'is_authenticated', False))
        try:
            enabled = indexing_enabled()
        except ImproperlyConfigured:
            enabled = False
        if not is_public or not enabled:
            response['X-Robots-Tag'] = 'noindex, nofollow'
        return response


@require_GET
def robots(request):
    if not indexing_enabled():
        return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain; charset=utf-8')
    private = ['/comptes/', '/studio/', '/credits/', '/admin/', '/administration/', '/i18n/', '/erreurs/']
    text = 'User-agent: *\nAllow: /\n' + ''.join(f'Disallow: {path}\n' for path in private)
    text += f'\nSitemap: {public_origin()}/sitemap.xml\n'
    return HttpResponse(text, content_type='text/plain; charset=utf-8')


@require_GET
def sitemap(request):
    if not indexing_enabled():
        return HttpResponse('Sitemap disponible après activation du domaine public.', status=404, content_type='text/plain; charset=utf-8')
    root = Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for language in ('fr', 'en'):
        url = SubElement(root, 'url')
        SubElement(url, 'loc').text = f'{public_origin()}/{language}/'
    return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='application/xml')
