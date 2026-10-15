from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from credits.models import CreditPurchase
from .middleware import COOKIE, VisitorMiddleware
from .models import DailyVisit


class DashboardTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='analytics-admin', is_staff=True)
        self.user = get_user_model().objects.create_user(username='analytics-user')
        self.client.force_login(self.admin)
        self.url = reverse('supervision:dashboard')

    def purchase(self, quantity=11, price='10', **extra):
        return CreditPurchase.objects.create(wallet=self.user.credit_wallet, quantity=quantity,
            price_usd=Decimal(price), pack='starter', environment='live', status='paid',
            paid_at=timezone.now(), currency='USD', amount_minor=int(Decimal(price) * 100), **extra)

    def test_access_is_staff_only_including_htmx(self):
        anonymous = Client()
        self.assertEqual(anonymous.get(self.url).status_code, 302)
        anonymous.force_login(self.user)
        self.assertEqual(anonymous.get(self.url).status_code, 403)
        self.assertEqual(anonymous.get(self.url, HTTP_HX_REQUEST='true').status_code, 403)
        response = self.client.get(self.url)
        self.assertContains(response, 'Visiteurs &amp; recettes')
        self.assertIn('no-store', response['Cache-Control'])

    def test_only_live_confirmed_revenue_refunds_on_their_own_date(self):
        self.purchase()
        self.purchase(quantity=28, price='25')
        sandbox = self.purchase(price='300')
        sandbox.environment = 'sandbox'
        sandbox.save()
        pending = self.purchase(price='150')
        pending.status, pending.paid_at = 'pending', None
        pending.save()
        old = self.purchase(price='50', refunded_at=timezone.now())
        old.paid_at = timezone.now() - timedelta(days=60)
        old.save()
        DailyVisit.objects.create(day=timezone.localdate(), visitor_hash='one', page_views=3)
        DailyVisit.objects.create(day=timezone.localdate() - timedelta(days=1), visitor_hash='one', page_views=2)
        response = self.client.get(self.url)
        metrics = response.context['metrics']
        self.assertEqual([m['value'] for m in metrics], [1, 5, Decimal('35'), Decimal('-15')])
        self.assertEqual(response.context['payment_count'], 2)
        self.assertEqual(response.context['credits_sold'], 39)
        self.assertEqual(response.context['refunded'], 50)
        self.assertEqual(DailyVisit.objects.count(), 2)  # Administrateur non comptabilisé.

    def test_xof_conversion_is_explicit_and_keeps_original_payment_amount(self):
        order = self.purchase()
        order.currency, order.quoted_amount = 'XOF', Decimal('5220.50')
        order.save()
        response = self.client.get(self.url, {'currency': 'XOF', 'rate': '600', 'period': '7'})
        self.assertEqual(response.context['metrics'][2]['value'], 6000)
        self.assertContains(response, 'Conversion indicative')
        self.assertContains(response, '5220,50 XOF')
        missing = self.client.get(self.url, {'currency': 'XOF'})
        self.assertEqual(missing.context['currency'], 'USD')
        self.assertTrue(missing.context['form'].errors)
        for rate in ('-1', 'NaN', 'Infinity', '0'):
            self.assertTrue(self.client.get(self.url, {'currency': 'XOF', 'rate': rate}).context['form'].errors)

    def test_htmx_partial_and_empty_period_have_zero_values(self):
        response = self.client.get(self.url, {'period': '7'}, HTTP_HX_REQUEST='true')
        self.assertNotContains(response, '<!DOCTYPE')
        self.assertContains(response, 'Aucun paiement live confirmé')
        self.assertEqual(len(response.context['rows']), 7)
        self.assertEqual([m['value'] for m in response.context['metrics']], [0, 0, 0, 0])


class VisitorTests(TestCase):
    def test_repeat_visits_one_unique_browser_new_client_is_distinct(self):
        client = Client()
        client.get('/')
        client.get('/')
        self.assertEqual(DailyVisit.objects.count(), 1)
        self.assertEqual(DailyVisit.objects.get().page_views, 2)
        self.assertTrue(client.cookies[COOKIE]['httponly'])
        Client().get('/')
        self.assertEqual(DailyVisit.objects.count(), 2)

    def test_bots_htmx_assets_and_administration_are_excluded(self):
        factory = RequestFactory()
        middleware = VisitorMiddleware(lambda request: HttpResponse('OK', content_type='text/html'))
        for path, headers in [('/', {'HTTP_USER_AGENT': 'ExampleBot'}),
                              ('/', {'HTTP_HX_REQUEST': 'true'}),
                              ('/administration/', {}), ('/admin/', {}), ('/static/test.css', {}),
                              ('/credits/callback/', {})]:
            request = factory.get(path, **headers)
            request.user = get_user_model()()
            middleware(request)
        self.assertEqual(DailyVisit.objects.count(), 0)

    def test_tracking_database_failure_never_breaks_page(self):
        request = RequestFactory().get('/')
        request.user = get_user_model()()
        middleware = VisitorMiddleware(lambda request: HttpResponse('Page disponible'))
        with patch('supervision.middleware.DailyVisit.objects.get_or_create', side_effect=DatabaseError):
            self.assertEqual(middleware(request).status_code, 200)
