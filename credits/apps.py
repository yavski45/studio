from django.apps import AppConfig
from django.conf import settings
from django.utils.autoreload import autoreload_started


def watch_environment(sender, **kwargs):
    sender.extra_files.add(settings.BASE_DIR / '.env')


class CreditsConfig(AppConfig):
    name = 'credits'

    def ready(self):
        from . import signals  # noqa: F401
        autoreload_started.connect(watch_environment, dispatch_uid='dublao.watch_environment')
