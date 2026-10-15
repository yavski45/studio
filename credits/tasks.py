import logging
from datetime import timedelta

from celery import shared_task
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError

from .geniuspay import PaymentUnavailable, configured, get_payment
from .models import CreditPurchase, PaymentWebhook
from .payments import apply_payment

logger = logging.getLogger(__name__)


def enqueue_webhook(pk):
    try:
        process_webhook.delay(pk)
    except (OperationalError, OSError):
        logger.warning('Publication du webhook différée ; notification %s.', pk)


@shared_task(ignore_result=True)
def dispatch_webhooks():
    now = timezone.now()
    due = PaymentWebhook.objects.filter(status__in=['pending', 'processing']).filter(
        Q(lease_until__isnull=True) | Q(lease_until__lt=now)).filter(
        Q(next_check_at__isnull=True) | Q(next_check_at__lte=now))
    for pk in due.values_list('pk', flat=True)[:100]:
        enqueue_webhook(pk)


@shared_task(ignore_result=True)
def process_webhook(pk):
    now = timezone.now()
    with transaction.atomic():
        receipt = PaymentWebhook.objects.select_for_update().filter(pk=pk).first()
        if not receipt or receipt.status not in ('pending', 'processing'):
            return
        if (receipt.lease_until and receipt.lease_until > now) or (receipt.next_check_at and receipt.next_check_at > now):
            return
        receipt.status, receipt.lease_until = 'processing', now + timedelta(minutes=2)
        receipt.save(update_fields=['status', 'lease_until'])
    try:
        data = get_payment(receipt.payment_reference)
        if data.get('reference') != receipt.payment_reference:
            raise ValueError('Référence incohérente.')
        # Une notification terminale peut précéder la mise à jour du GET.
        if receipt.event != 'payment.initiated' and data.get('status') in ('pending', 'processing'):
            raise PaymentUnavailable('Confirmation non disponible.')
        if receipt.event == 'payment.refunded' and data.get('status') == 'completed':
            raise PaymentUnavailable('Remboursement non confirmé.')
        with transaction.atomic():
            current = PaymentWebhook.objects.select_for_update().filter(pk=pk, status='processing',
                lease_until=receipt.lease_until).first()
            if not current:
                return  # Un autre worker a repris cette notification.
            apply_payment(receipt.purchase_id, data)
            PaymentWebhook.objects.filter(pk=pk).update(status='done', lease_until=None,
                next_check_at=None, error_code='', processed_at=timezone.now())
        logger.info('Notification Genius Pay traitée : %s (%s).', pk, receipt.event)
    except (PaymentUnavailable, ImproperlyConfigured):
        attempts = receipt.attempts + 1
        PaymentWebhook.objects.filter(pk=pk, status='processing', lease_until=receipt.lease_until).update(status='review' if attempts >= 20 else 'pending',
            attempts=attempts, lease_until=None, error_code='PROVIDER_UNAVAILABLE',
            next_check_at=now + timedelta(seconds=min(30 * 2 ** min(attempts, 7), 3600)))
        logger.warning('Confirmation du webhook différée ; notification %s.', pk)
    except ValueError:
        PaymentWebhook.objects.filter(pk=pk, status='processing', lease_until=receipt.lease_until).update(status='review', lease_until=None,
            error_code='PAYMENT_MISMATCH', attempts=receipt.attempts + 1)
        logger.warning('Notification à vérifier ; notification %s.', pk)


@shared_task(ignore_result=True)
def reconcile_payments():
    if not configured():
        return
    orders = CreditPurchase.objects.filter(status__in=['pending', 'review'],
        provider='geniuspay', provider_reference__isnull=False, paid_at__isnull=True,
        created_at__gte=timezone.now() - timedelta(days=7)).order_by('created_at')[:100]
    for order in orders:
        try:
            apply_payment(order.pk, get_payment(order.provider_reference))
        except (PaymentUnavailable, ImproperlyConfigured, ValueError):
            logger.warning('Vérification du paiement différée ; achat %s.', order.pk)
