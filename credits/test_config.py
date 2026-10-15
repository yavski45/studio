import os
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from . import config
from .geniuspay import webhook_secret


class ConfigurationTests(SimpleTestCase):
    def test_missing_django_alias_reads_dotenv_and_active_secret(self):
        with patch.object(config, 'settings', SimpleNamespace()), patch.dict(os.environ, {
                'GENIUSPAY_ENVIRONMENT': 'live', 'GENIUSPAY_MODE': '',
                'GENIUSPAY_WEBHOOK_SECRET_LIVE': 'fake-live',
                'GENIUSPAY_WEBHOOK_SECRET_SANDBOX': 'fake-sandbox'}, clear=True):
            self.assertEqual(config.payment_environment(), 'live')
            self.assertEqual(webhook_secret(), 'fake-live')

    def test_explicit_django_test_mode_overrides_environment(self):
        with patch.object(config, 'settings', SimpleNamespace(GENIUSPAY_MODE='sandbox')):
            self.assertEqual(config.payment_environment(), 'sandbox')

    def test_unknown_or_conflicting_modes_are_rejected(self):
        for overrides in ({'GENIUSPAY_MODE': 'production'},
                          {'GENIUSPAY_MODE': 'sandbox', 'GENIUSPAY_ENVIRONMENT': 'live'}):
            with patch.object(config, 'settings', SimpleNamespace(**overrides)):
                with self.assertRaises(ImproperlyConfigured):
                    config.payment_environment()
