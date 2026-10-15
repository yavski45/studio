"""Préparer la base Docker et les fichiers publics avant les services applicatifs."""
import os
import sys
from pathlib import Path

import django
from django.core.management import call_command


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dublao.settings')
    django.setup()
    call_command('migrate', interactive=False)
    call_command('collectstatic', interactive=False)
    from django.conf import settings
    from django.utils.translation import override
    from dublao.errors import ERRORS, error_html
    for language in ('fr', 'en'):
        directory = settings.STATIC_ROOT / 'dublao' / 'errors' / language
        directory.mkdir(parents=True, exist_ok=True)
        with override(language):
            for code in ERRORS:
                (directory / f'{code}.html').write_text(error_html(code), encoding='utf-8')


if __name__ == '__main__':
    main()
