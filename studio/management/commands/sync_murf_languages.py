import httpx
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from murf.core.api_error import ApiError

from studio.models import DubbingLanguage
from studio.murf_client import murf_client


class Command(BaseCommand):
    help = 'Actualise les langues Murf avec des appels de lecture, sans créer de doublage.'

    def handle(self, *args, **options):
        try:
            with murf_client() as client:
                sources = client.dubbing.languages.list_source_languages()
                targets = client.dubbing.languages.list_destination_languages()
            if not sources or not targets:
                raise CommandError('Catalogue vide ; la sélection actuelle est conservée.')
            with transaction.atomic():
                DubbingLanguage.objects.update(source=False, target=False)
                for lang in sources:
                    DubbingLanguage.objects.update_or_create(locale=lang.locale, defaults={'name': lang.language, 'source': True})
                for lang in targets:
                    if 'AUTOMATED' in (lang.supports or []):
                        DubbingLanguage.objects.update_or_create(locale=lang.locale, defaults={'name': lang.language, 'target': True})
        except (ApiError, httpx.HTTPError, ImproperlyConfigured) as error:
            raise CommandError(f'Catalogue Murf indisponible ({type(error).__name__}). Aucun secret affiché.') from None
        self.stdout.write(self.style.SUCCESS('Catalogue de langues actualisé.'))
