import hashlib
import hmac
import json
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from io import StringIO

import httpx
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from murf.core.api_error import ApiError
from kombu.exceptions import OperationalError

from studio.models import DubbingJob
from studio.tasks import process_job
from .models import CreditEntry, CreditPurchase, CreditWallet, PaymentWebhook, UNITS_PER_CREDIT
from .tasks import dispatch_webhooks, process_webhook
from .catalog import PACKS
from .geniuspay import PaymentUnavailable, api, create_payment
from .payments import apply_payment, bind_checkout_quote
from .services import InsufficientCredits, grant_credits, metered_units, reserve_job, settle_job


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WalletTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='wallet', email='wallet@example.com')
        self.wallet = self.user.credit_wallet
        self.job = DubbingJob.objects.create(user=self.user, title='Formation', source='test.mp4',
            original_name='test.mp4', target_locales=['en_US', 'es_ES'], credit_charge_required=True)

    def fund(self, amount=10):
        grant_credits(self.user, amount, 'test-funds')

    def balance(self):
        self.wallet.refresh_from_db()
        return self.wallet.available_credits

    def test_new_wallet_empty_and_grant_idempotent(self):
        self.assertEqual(self.balance(), 0)
        self.fund()
        self.fund()
        self.assertEqual(self.balance(), 10)
        self.assertEqual(CreditEntry.objects.count(), 1)
        with self.assertRaises(ValueError):
            grant_credits(self.user, 20, 'test-funds')

    def test_rounding_boundary(self):
        self.assertEqual(metered_units(60000, 'minute'), 60000)
        self.assertEqual(metered_units(60001, 'minute'), 120000)
        with self.assertRaises(ValueError):
            metered_units(0, 'minute')

    def test_insufficient_credits_no_reservation_or_debit(self):
        self.fund(3)
        with self.assertRaises(InsufficientCredits):
            reserve_job(self.job, 90000, 'minute')
        self.assertEqual(self.balance(), 3)
        self.assertFalse(hasattr(self.job, 'credit_reservation'))

    def test_started_minute_rounds_up_at_each_boundary(self):
        for duration, credits in [(1, 1), (20000, 1), (60000, 1), (60001, 2),
                                  (61000, 2), (80000, 2), (90000, 2),
                                  (120000, 2), (120001, 3), (121000, 3)]:
            with self.subTest(duration=duration):
                self.assertEqual(metered_units(duration, 'minute'), credits * 60000)
        with self.assertRaises(ValueError):
            metered_units(0, 'minute')

    def test_started_minute_reservation_and_successful_languages_only(self):
        self.fund(5)
        reservation = reserve_job(self.job, 80000, 'minute')
        self.assertEqual(reservation.reserved_credits, 4)
        self.assertEqual(self.balance(), 1)
        settled = settle_job(self.job, ['en_US'])
        self.assertEqual(settled.consumed_credits, 2)
        self.assertEqual(self.balance(), 3)

    def test_parallel_jobs_cannot_over_reserve_and_partial_result_releases(self):
        self.fund(5)
        reservation = reserve_job(self.job, 90000, 'minute')
        self.assertEqual(reserve_job(self.job, 90000, 'minute').pk, reservation.pk)
        self.assertEqual(self.balance(), 1)
        other = DubbingJob.objects.create(user=self.user, title='Autre', target_locales=['en_US'])
        with self.assertRaises(InsufficientCredits):
            reserve_job(other, 90000, 'minute')
        settle_job(self.job, ['en_US', 'unknown', 'en_US'])
        settle_job(self.job, ['en_US'])
        self.assertEqual(self.balance(), 3)
        self.assertEqual(CreditEntry.objects.filter(kind='settle').count(), 1)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.reserved_units, 0)

    def test_failure_releases_everything(self):
        self.fund()
        reserve_job(self.job, 90000, 'minute')
        settle_job(self.job, [])
        self.assertEqual(self.balance(), 10)

    def provider(self, error=None):
        client = Mock()
        client.dubbing.jobs.create.return_value = SimpleNamespace(job_id='provider-test')
        if error:
            client.dubbing.jobs.create.side_effect = error
        @contextmanager
        def factory():
            yield client
        return client, patch('studio.tasks.murf_client', factory)

    @patch('studio.tasks.video_duration_ms', return_value=90000)
    def test_no_provider_call_without_funds(self, duration):
        client, factory = self.provider()
        with factory:
            process_job(str(self.job.pk))
        client.dubbing.jobs.create.assert_not_called()
        self.job.refresh_from_db()
        self.assertEqual(self.job.error_code, 'INSUFFICIENT_USER_CREDITS')
        self.assertEqual(self.job.duration_ms, 90000)

    @patch('studio.tasks.video_duration_ms', return_value=90000)
    def test_network_ambiguity_holds_credit_and_never_reposts(self, duration):
        self.fund()
        client, factory = self.provider(httpx.ConnectError('connection lost'))
        with factory, patch('django.core.files.storage.InMemoryStorage.url', return_value='https://storage.example/video.mp4'):
            process_job(str(self.job.pk))
            process_job(str(self.job.pk))
        client.dubbing.jobs.create.assert_called_once()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'review')
        self.assertEqual(self.balance(), 6)

    @patch('studio.tasks.video_duration_ms', return_value=80000)
    def test_worker_reserves_started_minute_before_provider_call(self, duration):
        self.fund(5)
        client, factory = self.provider(httpx.ConnectError('connection lost'))
        with factory, patch('django.core.files.storage.InMemoryStorage.url', return_value='https://storage.example/video.mp4'):
            process_job(str(self.job.pk))
        client.dubbing.jobs.create.assert_called_once()
        self.job.refresh_from_db()
        self.assertEqual(self.job.credit_reservation.reserved_credits, 4)
        self.assertEqual(self.balance(), 1)

    @patch('studio.tasks.video_duration_ms', return_value=90000)
    def test_provider_rejection_returns_credit(self, duration):
        self.fund()
        _, factory = self.provider(ApiError(status_code=422, body={}))
        with factory, patch('django.core.files.storage.InMemoryStorage.url', return_value='https://storage.example/video.mp4'):
            process_job(str(self.job.pk))
        self.assertEqual(self.balance(), 10)

    def test_frozen_wallet_cannot_reserve(self):
        self.fund()
        self.wallet.frozen = True
        self.wallet.save()
        with self.assertRaises(InsufficientCredits):
            reserve_job(self.job, 90000, 'minute')


@override_settings(GENIUSPAY_API_KEY='pk_live_test', GENIUSPAY_API_SECRET='sk_live_test',
                  GENIUSPAY_WEBHOOK_SECRET='test-webhook', GENIUSPAY_ENVIRONMENT='live',
                  GENIUSPAY_WEBHOOK_SECRET_LIVE='test-webhook', GENIUSPAY_WEBHOOK_SECRET_SANDBOX='test-sandbox',
                  GENIUSPAY_ACCEPT_XOF_CONVERSION=False,
                  PAYMENT_PUBLIC_URL='https://dublao.example')
class PaymentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='payer', email='payer@example.com')
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True)
        self.client.force_login(self.user)
        self.order = CreditPurchase.objects.create(wallet=self.user.credit_wallet, quantity=11, pack='starter',
            price_usd=Decimal('10.00'), currency='USD', amount_minor=1000, provider='geniuspay',
            environment='live', provider_reference='MTX-TEST', status='pending')

    def payment(self, **overrides):
        return dict(reference='MTX-TEST', amount=10, currency='USD', environment='live', status='completed',
            metadata={'order_id': str(self.order.pk), 'user_id': str(self.user.pk)}, **overrides)

    def webhook(self, data=None, signature=None, timestamp=None, event='payment.success', event_id='test-event-001', environment='live', header_event=None):
        data = dict(self.payment() if data is None else data)
        data.pop('environment', None)  # Format du guide Genius Pay : environnement à la racine.
        body = json.dumps({'id': event_id, 'event': event, 'environment': environment, 'data': data},
                          ensure_ascii=False, indent=2).encode()
        timestamp = timestamp or str(int(time.time()))
        signature = signature or hmac.new(b'test-webhook', timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        return self.client.post(reverse('credits:webhook'), body, content_type='application/json',
            HTTP_X_WEBHOOK_SIGNATURE=signature, HTTP_X_WEBHOOK_TIMESTAMP=timestamp,
            HTTP_X_WEBHOOK_ENVIRONMENT=environment, HTTP_X_WEBHOOK_EVENT=header_event or event)

    def test_confirmation_exactly_once(self):
        apply_payment(self.order.pk, self.payment())
        apply_payment(self.order.pk, self.payment())
        self.user.credit_wallet.refresh_from_db()
        self.assertEqual(self.user.credit_wallet.available_credits, 11)
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)

    def test_successive_packs_increment_existing_wallet_without_duplicate_credit(self):
        apply_payment(self.order.pk, self.payment())
        creator = CreditPurchase.objects.create(wallet=self.user.credit_wallet,
            quantity=28, pack='creator', price_usd=Decimal('25.00'), currency='USD',
            amount_minor=2500, provider='geniuspay', environment='live',
            provider_reference='MTX-CREATOR', status='pending')
        data = dict(reference='MTX-CREATOR', amount=25, currency='USD',
            environment='live', status='completed',
            metadata={'order_id': str(creator.pk), 'user_id': str(self.user.pk)})
        apply_payment(creator.pk, data)
        apply_payment(creator.pk, data)
        wallet = self.user.credit_wallet
        wallet.refresh_from_db()
        self.assertEqual(wallet.available_credits, 39)
        self.assertEqual(CreditEntry.objects.filter(wallet=wallet, kind='purchase').count(), 2)
        job = DubbingJob.objects.create(user=self.user, title='Après recharge',
            target_locales=['en_US', 'es_ES'], credit_charge_required=True)
        reserve_job(job, 90000, 'minute')
        settle_job(job, ['en_US', 'es_ES'])
        apply_payment(self.order.pk, self.payment())
        apply_payment(creator.pk, data)
        wallet.refresh_from_db()
        self.assertEqual(wallet.available_credits, 35)
        self.assertEqual(CreditEntry.objects.filter(wallet=wallet, kind='purchase').count(), 2)

    def test_amount_currency_identity_environment_must_match(self):
        for key, value in [('amount', 500), ('currency', 'XOF'), ('environment', 'sandbox'), ('reference', 'other'), ('metadata', {})]:
            data = self.payment()
            data[key] = value
            with self.assertRaises(ValueError):
                apply_payment(self.order.pk, data)
        self.assertEqual(CreditEntry.objects.count(), 0)

    def test_sandbox_payment_does_not_fund_real_wallet(self):
        self.order.environment = 'sandbox'
        self.order.save()
        data = self.payment()
        data['environment'] = 'sandbox'
        apply_payment(self.order.pk, data)
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.get_payment')
    def test_browser_return_cannot_mint_credits_and_private_order(self, get):
        data = self.payment()
        data['status'] = 'pending'
        get.return_value = data
        self.client.get(reverse('credits:purchase', args=[self.order.pk]) + '?status=completed')
        self.assertEqual(CreditEntry.objects.count(), 0)
        other = get_user_model().objects.create_user(username='other-payer', email='other@example.com')
        EmailAddress.objects.create(user=other, email=other.email, verified=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('credits:purchase', args=[self.order.pk])).status_code, 404)

    @patch('credits.tasks.get_payment')
    def test_signed_webhook_reverified_and_duplicate_delivery(self, get):
        get.return_value = self.payment()
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(self.webhook().status_code, 200)
        get.assert_not_called()
        self.assertEqual(PaymentWebhook.objects.count(), 1)
        self.assertEqual(CreditEntry.objects.count(), 0)
        process_webhook(PaymentWebhook.objects.get().pk)
        process_webhook(PaymentWebhook.objects.get().pk)
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)
        get.assert_called_once_with('MTX-TEST')

    @patch('credits.tasks.get_payment')
    def test_invalid_and_stale_webhooks_never_call_provider(self, get):
        self.assertEqual(self.webhook(signature='bad').status_code, 401)
        self.assertEqual(self.webhook(timestamp=str(int(time.time()) - 600)).status_code, 400)
        get.assert_not_called()

    @patch('credits.tasks.get_payment')
    def test_valid_signature_insufficient_without_verified_amount(self, get):
        get.return_value = self.payment()
        get.return_value['amount'] = 100
        self.assertEqual(self.webhook().status_code, 200)
        process_webhook(PaymentWebhook.objects.get().pk)
        self.assertEqual(PaymentWebhook.objects.get().status, 'review')
        self.assertEqual(CreditEntry.objects.count(), 0)

    def test_refund_freezes_wallet_and_old_success_cannot_recredit(self):
        apply_payment(self.order.pk, self.payment())
        data = self.payment()
        data['status'] = 'refunded'
        apply_payment(self.order.pk, data)
        apply_payment(self.order.pk, self.payment())
        self.user.credit_wallet.refresh_from_db()
        self.assertTrue(self.user.credit_wallet.frozen)
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)

    def test_refund_received_before_success_prevents_future_credit(self):
        data = self.payment()
        data['status'] = 'refunded'
        apply_payment(self.order.pk, data)
        apply_payment(self.order.pk, self.payment())
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.refunded_at)
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.create_payment')
    def test_checkout_server_price_and_repeated_form_no_duplicate_post(self, create):
        token = uuid.uuid4()
        data = self.payment()
        data['metadata']['order_id'] = str(token)
        data['reference'] = 'MTX-NEW'
        create.return_value = data, 'https://geniuspay.ci/checkout/MTX-NEW'
        payload = {'submission_id': str(token), 'pack': 'starter', 'quantity': 99999, 'price': 1}
        self.assertEqual(self.client.post(reverse('credits:buy'), payload).status_code, 302)
        self.client.post(reverse('credits:buy'), payload)
        create.assert_called_once()
        self.assertEqual(create.call_args.args[1], reverse('credits:callback') + '?purchase=' + str(token))
        order = CreditPurchase.objects.get(pk=token)
        self.assertEqual(order.amount_minor, 1000)
        self.assertEqual(order.quantity, 11)
        self.assertEqual(order.price_usd, Decimal('10.00'))

    def test_wallet_requires_verified_account_and_renders(self):
        response = self.client.get(reverse('credits:wallet'))
        self.assertContains(response, 'Mon portefeuille')
        self.assertNotContains(response, 'Paiement de test')
        EmailAddress.objects.filter(user=self.user).update(verified=False)
        self.assertEqual(self.client.get(reverse('credits:wallet')).status_code, 403)

    @patch('credits.geniuspay.api')
    def test_provider_request_usd_major_units_and_safe_redirect(self, api):
        api.return_value = {**self.payment(), 'checkout_url': 'https://geniuspay.ci/checkout/MTX-TEST'}
        create_payment(self.order, '/credits/achats/test/')
        payload = api.call_args.args[2]
        self.assertEqual(payload['success_url'], 'https://dublao.example/credits/achats/test/')
        self.assertEqual(payload['error_url'], payload['success_url'])
        self.assertEqual(payload['currency'], 'USD')
        self.assertEqual(payload['amount'], 10)
        self.assertEqual(payload['metadata']['order_id'], str(self.order.pk))
        api.return_value['checkout_url'] = 'https://evil.example/checkout'
        with self.assertRaises(PaymentUnavailable):
            create_payment(self.order, '/credits/achats/test/')

    @patch('credits.views.create_payment')
    def test_all_pack_prices_are_server_catalog(self, create):
        for key, offer in PACKS.items():
            token = uuid.uuid4()
            data = self.payment()
            data.update(reference='MTX-' + key, amount=int(offer['usd']),
                        metadata={'order_id': str(token), 'user_id': str(self.user.pk)})
            create.return_value = data, 'https://geniuspay.ci/checkout/MTX-' + key
            result = self.client.post(reverse('credits:buy'), {'submission_id': token, 'pack': key, 'amount': 1, 'quantity': 99999})
            self.assertEqual(result.status_code, 302)
            order = CreditPurchase.objects.get(pk=token)
            self.assertEqual(order.quantity, offer['quantity'])
            self.assertEqual(order.price_usd, offer['usd'])
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.create_payment')
    def test_checkout_in_foreign_currency_keeps_reference_but_blocks_redirect_and_credit(self, create):
        token = uuid.uuid4()
        data = self.payment()
        data.update(reference='MTX-CONVERTED', amount=6000, currency='XOF',
                    metadata={'order_id': str(token), 'user_id': str(self.user.pk)})
        create.return_value = data, 'https://geniuspay.ci/checkout/MTX-CONVERTED'
        response = self.client.post(reverse('credits:buy'), {'submission_id': token, 'pack': 'starter'})
        self.assertRedirects(response, reverse('credits:purchase', args=[token]) + '?details=1')
        order = CreditPurchase.objects.get(pk=token)
        self.assertEqual(order.status, 'review')
        self.assertEqual(order.error_code, 'PAYMENT_CURRENCY_MISMATCH')
        self.assertEqual(order.provider_reference, 'MTX-CONVERTED')
        self.assertEqual(order.checkout_url, '')
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.get_payment')
    @patch('credits.views.create_payment')
    def test_incomplete_checkout_response_is_retrieved_before_validation(self, create, get):
        token = uuid.uuid4()
        data = self.payment()
        data.update(reference='MTX-INCOMPLETE', metadata={'order_id': str(token), 'user_id': str(self.user.pk)})
        create.return_value = {'reference': 'MTX-INCOMPLETE'}, 'https://geniuspay.ci/checkout/MTX-INCOMPLETE'
        get.return_value = data
        response = self.client.post(reverse('credits:buy'), {'submission_id': token, 'pack': 'starter'})
        self.assertEqual(response.url, 'https://geniuspay.ci/checkout/MTX-INCOMPLETE')
        get.assert_called_once_with('MTX-INCOMPLETE')
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.create_payment', side_effect=PaymentUnavailable('Rejet', http_status=422,
           provider_code='VALIDATION_ERROR', rejected_fields=('amount',)))
    def test_confirmed_validation_rejection_does_not_suggest_payment_in_progress(self, create):
        token = uuid.uuid4()
        with self.assertLogs('credits.views', 'WARNING') as captured:
            self.client.post(reverse('credits:buy'), {'submission_id': token, 'pack': 'starter'})
        self.assertEqual(CreditPurchase.objects.get(pk=token).status, 'failed')
        self.assertIn('HTTP 422', captured.output[0])
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.geniuspay.requests.request')
    def test_api_error_keeps_safe_diagnostics_and_no_response_secrets(self, request):
        request.return_value.status_code = 422
        request.return_value.json.return_value = {'success': False,
            'error': {'code': 'VALIDATION_ERROR', 'message': 'private response'},
            'errors': {'amount': ['private field value'], 'secret': ['private key']}}
        with self.assertRaises(PaymentUnavailable) as caught:
            api('POST', 'payments', {'amount': 10, 'currency': 'USD'})
        self.assertEqual(caught.exception.http_status, 422)
        self.assertEqual(caught.exception.provider_code, 'VALIDATION_ERROR')
        self.assertEqual(caught.exception.rejected_fields, ('amount',))
        self.assertNotIn('private', str(caught.exception))

    @patch('credits.views.get_payment')
    def test_htmx_return_confirmation_updates_wallet_once(self, get):
        get.return_value = self.payment()
        self.order.error_code = 'PROVIDER_UNAVAILABLE'
        self.order.save(update_fields=['error_code'])
        url = reverse('credits:verify', args=[self.order.pk])
        response = self.client.post(url, HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Vos crédits sont disponibles')
        self.assertNotContains(response, '<!DOCTYPE')
        self.assertEqual(response['HX-Redirect'], reverse('credits:wallet'))
        self.client.post(url, HTTP_HX_REQUEST='true')
        get.assert_called_once_with('MTX-TEST')
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.error_code, '')

    @patch('credits.views.get_payment')
    @override_settings(GENIUSPAY_ENVIRONMENT='sandbox')
    def test_live_checkout_cannot_be_resumed_or_verified_in_sandbox(self, get):
        self.order.checkout_url = 'https://geniuspay.ci/checkout/MTX-TEST'
        self.order.save(update_fields=['checkout_url'])
        response = self.client.get(reverse('credits:purchase', args=[self.order.pk]) + '?details=1')
        self.assertNotContains(response, self.order.checkout_url)
        self.assertContains(response, 'autre mode de paiement')
        self.assertRedirects(self.client.post(reverse('credits:verify', args=[self.order.pk])), reverse('credits:wallet'))
        self.assertRedirects(self.client.get(reverse('credits:callback'), {'purchase': self.order.pk}), reverse('credits:wallet'))
        get.assert_not_called()
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.get_payment')
    def test_fixed_callback_confirms_owned_purchase_and_returns_to_wallet(self, get):
        get.return_value = self.payment()
        self.assertRedirects(self.client.get(reverse('credits:callback'), {'purchase': str(self.order.pk)}), reverse('credits:wallet'))
        get.assert_called_once_with('MTX-TEST')
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)

    @patch('credits.views.get_payment')
    def test_fixed_callback_without_purchase_or_invalid_id_returns_without_credits(self, get):
        for params in ({}, {'purchase': 'invalid', 'status': 'completed'}):
            self.assertRedirects(self.client.get(reverse('credits:callback'), params), reverse('credits:wallet'))
        get.assert_not_called()
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.get_payment')
    def test_fixed_callback_cannot_confirm_another_users_purchase(self, get):
        other = get_user_model().objects.create_user(username='callback-other', email='callback-other@example.com')
        EmailAddress.objects.create(user=other, email=other.email, verified=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('credits:callback'), {'purchase': str(self.order.pk)}).status_code, 404)
        get.assert_not_called()

    @patch('credits.views.get_payment')
    def test_checkout_return_confirms_server_payment_then_redirects_to_wallet_once(self, get):
        get.return_value = self.payment()
        url = reverse('credits:return', args=[self.order.pk])
        self.assertRedirects(self.client.get(url), reverse('credits:wallet'))
        self.assertRedirects(self.client.get(url), reverse('credits:wallet'))
        get.assert_called_once_with('MTX-TEST')
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)

    @patch('credits.views.get_payment')
    def test_cancelled_payment_returns_to_wallet_without_credits(self, get):
        data = self.payment()
        data['status'] = 'cancelled'
        get.return_value = data
        self.assertRedirects(self.client.get(reverse('credits:return', args=[self.order.pk])), reverse('credits:wallet'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'failed')
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.get_payment')
    def test_abandoned_or_forged_success_return_cannot_add_credit(self, get):
        data = self.payment()
        data['status'] = 'pending'
        get.return_value = data
        url = reverse('credits:return', args=[self.order.pk]) + '?status=completed&success=true'
        self.assertRedirects(self.client.get(url), reverse('credits:wallet'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.get_payment', side_effect=PaymentUnavailable('provider unavailable'))
    def test_return_api_outage_still_redirects_to_wallet_without_credit(self, get):
        self.assertRedirects(self.client.get(reverse('credits:return', args=[self.order.pk])), reverse('credits:wallet'))
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.views.get_payment')
    def test_return_cannot_read_or_confirm_another_users_purchase(self, get):
        other = get_user_model().objects.create_user(username='return-other', email='return-other@example.com')
        EmailAddress.objects.create(user=other, email=other.email, verified=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('credits:return', args=[self.order.pk])).status_code, 404)
        get.assert_not_called()

    @patch('credits.views.get_payment', side_effect=PaymentUnavailable('provider unavailable'))
    def test_htmx_provider_outage_keeps_pending_manual_retry_without_auto_loop(self, get):
        response = self.client.post(reverse('credits:verify', args=[self.order.pk]), HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Vérifier le paiement')
        self.assertNotContains(response, 'load delay:500ms')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')
        self.assertEqual(CreditEntry.objects.count(), 0)

    def test_rejected_purchase_retries_with_same_pack_new_submission(self):
        self.order.status = 'failed'
        self.order.save(update_fields=['status'])
        response = self.client.get(reverse('credits:purchase', args=[self.order.pk]) + '?details=1')
        self.assertContains(response, 'Réessayer l’achat')
        response = self.client.get(reverse('credits:wallet') + '?pack=pro')
        self.assertEqual(response.context['selected_pack'], 'pro')
        self.assertEqual(response.context['selected_offer']['quantity'], 57)
        self.assertEqual(response.context['selected_offer']['usd'], Decimal('50.00'))
        self.assertEqual(response.context['pack_quantities']['pro'], 57)
        self.assertContains(response, '57 crédits</p>')
        self.assertNotEqual(str(response.context['form']['submission_id'].value()), str(self.order.pk))

    @patch('credits.views.get_payment')
    def test_old_checkout_return_redirects_to_wallet_and_keeps_history_details(self, get):
        data = self.payment()
        data['status'] = 'pending'
        get.return_value = data
        old_return = reverse('credits:purchase', args=[self.order.pk])
        self.assertRedirects(self.client.get(old_return), reverse('credits:wallet'))
        self.assertContains(self.client.get(old_return + '?details=1'), '11 crédits')
        get.assert_called_once_with('MTX-TEST')
        self.assertEqual(CreditEntry.objects.count(), 0)

    def converted_checkout(self, create, *, amount=6000):
        token = uuid.uuid4()
        data = self.payment()
        data.update(reference='MTX-' + str(token), amount=amount, currency='XOF', status='pending',
                    metadata={'order_id': str(token), 'user_id': str(self.user.pk)})
        create.return_value = data, 'https://geniuspay.ci/checkout/' + data['reference']
        response = self.client.post(reverse('credits:buy'), {'submission_id': token, 'pack': 'starter'})
        return CreditPurchase.objects.get(pk=token), data, response

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    @patch('credits.views.create_payment')
    def test_provider_xof_quote_is_saved_and_verified_exactly_once(self, create):
        order, data, response = self.converted_checkout(create)
        self.assertEqual(response.url, order.checkout_url)
        self.assertEqual(order.price_usd, Decimal('10.00'))
        self.assertEqual(order.currency, 'XOF')
        self.assertEqual(order.amount_minor, 6000)
        self.assertIsNotNone(order.quoted_at)
        self.assertEqual(CreditEntry.objects.count(), 0)
        data['status'] = 'completed'
        with patch('credits.views.get_payment', return_value=data):
            self.client.post(reverse('credits:verify', args=[order.pk]), HTTP_HX_REQUEST='true')
            self.client.post(reverse('credits:verify', args=[order.pk]), HTTP_HX_REQUEST='true')
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)
        self.user.credit_wallet.refresh_from_db()
        self.assertEqual(self.user.credit_wallet.available_credits, 11)

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    @patch('credits.views.create_payment')
    def test_xof_quote_cannot_be_changed_by_confirmation_or_later_quote(self, create):
        order, data, _ = self.converted_checkout(create)
        data.update(status='completed', amount=6001)
        with self.assertRaises(ValueError):
            apply_payment(order.pk, data)
        with self.assertRaises(ValueError):
            bind_checkout_quote(order, data)
        order.refresh_from_db()
        self.assertEqual(order.amount_minor, 6000)
        self.assertEqual(CreditEntry.objects.count(), 0)

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    @patch('credits.views.create_payment')
    def test_invalid_xof_quotes_never_propose_a_checkout(self, create):
        for amount in (0, -1, '6000.005', 'NaN', 'Infinity', '999999999999999999999'):
            order, data, response = self.converted_checkout(create, amount=amount)
            self.assertEqual(order.status, 'review')
            self.assertIsNone(order.quoted_at)
            self.assertEqual(order.checkout_url, '')
        self.assertEqual(CreditEntry.objects.count(), 0)

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    @patch('credits.views.create_payment')
    def test_fractional_xof_amount_is_preserved_without_rounding(self, create):
        order, data, response = self.converted_checkout(create, amount='5220.5')
        self.assertEqual(response.url, order.checkout_url)
        self.assertEqual(order.quoted_amount, Decimal('5220.50'))
        self.assertEqual(order.payment_amount, Decimal('5220.50'))
        self.assertIsNone(order.amount_minor)
        data['status'] = 'completed'
        for wrong in ('5220', '5221', '5220.51'):
            changed = {**data, 'amount': wrong}
            with self.assertRaises(ValueError):
                apply_payment(order.pk, changed)
        self.assertEqual(CreditEntry.objects.count(), 0)
        apply_payment(order.pk, data)
        apply_payment(order.pk, data)
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    def test_optional_null_original_fields_do_not_reject_valid_quote(self):
        data = self.payment()
        data.update(amount='5220.5', currency='XOF', status='pending',
                    original_amount=None, original_currency=None)
        bind_checkout_quote(self.order, data)
        self.assertEqual(self.order.quoted_amount, Decimal('5220.50'))

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    @patch('credits.management.commands.recover_genius_checkout.get_payment')
    def test_recover_existing_fractional_checkout_without_new_payment_or_credit(self, get):
        self.order.status, self.order.error_code = 'review', 'PAYMENT_AMOUNT_MISMATCH'
        self.order.save(update_fields=['status', 'error_code'])
        data = self.payment()
        data.update(amount='5220.5', currency='XOF', status='pending')
        get.return_value = data
        call_command('recover_genius_checkout', str(self.order.pk), stdout=StringIO())
        self.order.refresh_from_db()
        self.assertEqual(self.order.quoted_amount, Decimal('5220.50'))
        self.assertEqual(self.order.status, 'pending')
        self.assertEqual(self.order.checkout_url, 'https://geniuspay.ci/checkout/MTX-TEST')
        self.assertEqual(CreditPurchase.objects.count(), 1)
        self.assertEqual(CreditEntry.objects.count(), 0)

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    @patch('credits.management.commands.recover_genius_checkout.get_payment')
    def test_recovery_cannot_change_a_completed_transaction(self, get):
        self.order.status, self.order.error_code = 'review', 'PAYMENT_AMOUNT_MISMATCH'
        self.order.save(update_fields=['status', 'error_code'])
        get.return_value = self.payment()
        with self.assertRaises(CommandError):
            call_command('recover_genius_checkout', str(self.order.pk), stdout=StringIO())
        self.order.refresh_from_db()
        self.assertIsNone(self.order.quoted_amount)
        self.assertEqual(self.order.status, 'review')
        self.assertEqual(CreditEntry.objects.count(), 0)

    @override_settings(GENIUSPAY_ACCEPT_XOF_CONVERSION=True)
    def test_webhook_and_confirmation_cannot_bind_a_conversion_themselves(self):
        data = self.payment()
        data.update(currency='XOF', amount=6000)
        with self.assertRaises(ValueError):
            apply_payment(self.order.pk, data)
        self.assertEqual(self.webhook(data=data).status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.currency, 'USD')
        self.assertIsNone(self.order.quoted_at)
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.tasks.get_payment')
    def test_dashboard_webhook_test_never_creates_purchase_or_credit(self, get):
        result = self.webhook(data={'object': 'webhook.test', 'message': 'Test Genius Pay'}, event='webhook.test')
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()['success'])
        self.assertEqual(PaymentWebhook.objects.count(), 0)
        self.assertEqual(CreditEntry.objects.count(), 0)
        get.assert_not_called()

    def test_header_event_required_and_environment_must_agree(self):
        self.assertEqual(self.webhook(header_event='payment.failed').status_code, 400)
        self.assertEqual(self.webhook(environment='sandbox').status_code, 400)
        self.assertEqual(self.client.post(reverse('credits:webhook'), '{}', content_type='application/json').status_code, 400)
        self.assertEqual(PaymentWebhook.objects.count(), 0)

    @patch('credits.tasks.process_webhook.delay', side_effect=OperationalError('redis unavailable'))
    def test_broker_outage_does_not_lose_receipt_or_delay_http(self, delay):
        self.assertEqual(self.webhook().status_code, 200)
        delay.assert_not_called()
        dispatch_webhooks()
        delay.assert_called_once()
        self.assertEqual(PaymentWebhook.objects.get().status, 'pending')

    @patch('credits.tasks.get_payment', side_effect=PaymentUnavailable('provider unavailable'))
    def test_provider_outage_leaves_durable_retry_without_credits(self, get):
        self.webhook()
        receipt = PaymentWebhook.objects.get()
        process_webhook(receipt.pk)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, 'pending')
        self.assertEqual(receipt.attempts, 1)
        self.assertIsNotNone(receipt.next_check_at)
        process_webhook(receipt.pk)
        get.assert_called_once()
        self.assertEqual(CreditEntry.objects.count(), 0)

    @patch('credits.tasks.get_payment')
    def test_terminal_notification_waits_for_confirmed_provider_state(self, get):
        data = self.payment()
        data['status'] = 'processing'
        get.return_value = data
        self.webhook()
        receipt = PaymentWebhook.objects.get()
        process_webhook(receipt.pk)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, 'pending')
        self.assertEqual(CreditEntry.objects.count(), 0)
        receipt.next_check_at = None
        receipt.save()
        get.return_value = self.payment()
        process_webhook(receipt.pk)
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)

    @patch('credits.tasks.get_payment')
    def test_delayed_failure_notification_cannot_undo_verified_success(self, get):
        get.return_value = self.payment()
        data = self.payment()
        data['status'] = 'failed'
        self.webhook(data=data, event='payment.failed')
        process_webhook(PaymentWebhook.objects.get().pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertEqual(CreditEntry.objects.filter(kind='purchase').count(), 1)

    @patch('credits.tasks.get_payment')
    def test_refund_not_confirmed_by_api_never_freezes_wallet(self, get):
        apply_payment(self.order.pk, self.payment())
        get.return_value = self.payment()
        data = self.payment()
        data['status'] = 'refunded'
        self.webhook(data=data, event='payment.refunded')
        receipt = PaymentWebhook.objects.get()
        process_webhook(receipt.pk)
        self.user.credit_wallet.refresh_from_db()
        self.assertFalse(self.user.credit_wallet.frozen)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, 'pending')
