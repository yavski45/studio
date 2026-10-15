from django.apps import AppConfig


class ComptesConfig(AppConfig):
    name = 'comptes'

    def ready(self):
        from . import signals  # noqa: F401
