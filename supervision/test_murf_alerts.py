from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError

from studio.models import DubbingJob
from .models import MurfCreditStatus
from .murf_alerts import alert_context, observe_balance
from .tasks import refresh_murf_credits


@override_settings(MURFDUB_ENABLED=True, MURFDUB_API_KEY='test-murf-alert-key')
class MurfAlertTests(TestCase):
    def test_threshold_zero_unknown_and_invalid_values(self):
        self.assertEqual(alert_context()['level'], 'unknown')
        for balance, level in [(21, 'ok'), (20, 'low'), (1, 'low'), (0, 'empty')]:
            observe_balance(balance, timezone.now())
            self.assertEqual(alert_context()['level'], level)
        for invalid in (None, -1, True, '20'):
            observe_balance(invalid, timezone.now())
        self.assertEqual(alert_context()['remaining'], 0)

    def test_late_response_never_overwrites_newer_balance_and_key_change_hides_old_balance(self):
        observe_balance(10, timezone.now())
        observe_balance(100, timezone.now() - timedelta(minutes=1))
        self.assertEqual(alert_context()['remaining'], 10)
        with override_settings(MURFDUB_API_KEY='other-key'):
            self.assertEqual(alert_context()['level'], 'unknown')

    def test_read_only_status_refresh_does_not_create_a_dubbing(self):
        user = get_user_model().objects.create_user(username='murf-status-user')
        DubbingJob.objects.create(user=user, title='Test', murf_job_id='murf-balance-test')
        client = Mock()
        client.dubbing.jobs.get_status.return_value = SimpleNamespace(job_id='murf-balance-test', credits_remaining=18)
        @contextmanager
        def factory():
            yield client
        with patch('supervision.tasks.murf_client', factory):
            refresh_murf_credits()
        self.assertEqual(alert_context()['level'], 'low')
        client.dubbing.jobs.create.assert_not_called()
        client.dubbing.jobs.get_status.assert_called_once()

    def test_provider_failure_keeps_last_known_balance(self):
        user = get_user_model().objects.create_user(username='murf-outage-user')
        DubbingJob.objects.create(user=user, title='Test', murf_job_id='murf-balance-test')
        observe_balance(12, timezone.now())
        with patch('supervision.tasks.murf_client', side_effect=httpx.ConnectError('offline')):
            refresh_murf_credits()
        self.assertEqual(alert_context()['remaining'], 12)
        self.assertEqual(alert_context()['error'], 'PROVIDER_UNAVAILABLE')
        self.assertIsNone(MurfCreditStatus.objects.get(pk=1).refresh_lease_until)

    def test_no_job_is_unknown_not_zero(self):
        refresh_murf_credits()
        self.assertEqual(alert_context()['level'], 'unknown')
        self.assertEqual(alert_context()['error'], 'NO_JOB')

    @patch('supervision.views.refresh_murf_credits.delay', side_effect=OperationalError('offline'))
    def test_alert_and_refresh_staff_only_and_queue_outage_visible(self, delay):
        user = get_user_model().objects.create_user(username='murf-staff-user')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('supervision:murf-alert')).status_code, 403)
        self.assertEqual(self.client.post(reverse('supervision:murf-refresh')).status_code, 403)
        delay.assert_not_called()
        user.is_staff = True
        user.save()
        observe_balance(20, timezone.now())
        self.assertContains(self.client.get(reverse('supervision:murf-alert')), 'Recharge Murf Dub à prévoir')
        response = self.client.post(reverse('supervision:murf-refresh'), HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Vérifiez Celery et Redis')
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        self.assertEqual(csrf_client.post(reverse('supervision:murf-refresh')).status_code, 403)
