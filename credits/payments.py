from django.utils.translation import gettext_lazy
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import CreditEntry, CreditPurchase, CreditWallet, UNITS_PER_CREDIT
from .services import record
from .config import accepts_xof_conversion


class PaymentMismatch(ValueError):
    def __init__(self, code):
        super().__init__(gettext_lazy('Les informations du paiement ne correspondent pas à cet achat.'))
        self.code = code


def validate_reference(purchase, data):
    reference = data.get('reference') if isinstance(data, dict) else None
    if (not isinstance(reference, str) or not 0 < len(reference) <= 150
            or (purchase.provider_reference and reference != purchase.provider_reference)):
        raise PaymentMismatch('PAYMENT_IDENTITY_MISMATCH')


def validate_identity(purchase, data):
    validate_reference(purchase, data)
    try:
        metadata = data.get('metadata') or {}
        valid = (metadata.get('order_id') == str(purchase.pk)
            and str(metadata.get('user_id')) == str(purchase.wallet.user_id))
    except (TypeError, AttributeError):
        valid = False
    if not valid:
        raise PaymentMismatch('PAYMENT_IDENTITY_MISMATCH')
    if data.get('environment') != purchase.environment:
        raise PaymentMismatch('PAYMENT_ENVIRONMENT_MISMATCH')


def validate_payment(purchase, data):
    validate_identity(purchase, data)
    if data.get('currency') != purchase.currency:
        raise PaymentMismatch('PAYMENT_CURRENCY_MISMATCH')
    try:
        valid = Decimal(str(data.get('amount'))) == purchase.payment_amount
    except (InvalidOperation, TypeError, AttributeError):
        valid = False
    if not valid:
        raise PaymentMismatch('PAYMENT_AMOUNT_MISMATCH')


def bind_checkout_quote(purchase, data):
    """Fige le montant d'une création authentifiée ; jamais depuis un webhook."""
    validate_identity(purchase, data)
    if purchase.quoted_at or purchase.paid_at or purchase.refunded_at:
        validate_payment(purchase, data)
        return
    currency = data.get('currency')
    if currency not in ('USD', 'XOF') or (currency == 'XOF' and not accepts_xof_conversion()):
        raise PaymentMismatch('PAYMENT_CURRENCY_MISMATCH')
    if currency == 'XOF' and data.get('status') not in ('pending', 'processing'):
        raise PaymentMismatch('PAYMENT_STATE_MISMATCH')
    try:
        amount = Decimal(str(data.get('amount')))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
        if currency == 'USD' and amount != purchase.price_usd:
            raise InvalidOperation
        cents = amount * 100
        if cents != cents.to_integral_value() or amount > Decimal('999999999999999999.99'):
            raise InvalidOperation
        # Si le prestataire expose le montant d'origine, il doit aussi concorder.
        if (data.get('original_amount') is not None and Decimal(str(data['original_amount'])) != purchase.price_usd):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        raise PaymentMismatch('PAYMENT_AMOUNT_MISMATCH') from None
    if data.get('original_currency') not in (None, 'USD'):
        raise PaymentMismatch('PAYMENT_CURRENCY_MISMATCH')
    purchase.currency, purchase.quoted_amount = currency, amount
    # Compatibilité des anciennes écritures : leur colonne XOF était entière.
    # Une quote décimale utilise exclusivement quoted_amount, sans arrondi.
    minor = amount * 100 if currency == 'USD' else amount
    purchase.amount_minor = int(minor) if minor == minor.to_integral_value() and minor <= 9223372036854775807 else None
    purchase.quoted_at = timezone.now()


@transaction.atomic
def apply_payment(purchase_id, data):
    """Uniquement après un GET authentifié vers Genius Pay ; jamais depuis le navigateur."""
    snapshot = CreditPurchase.objects.select_related('wallet').get(pk=purchase_id)
    wallet = CreditWallet.objects.select_for_update().get(pk=snapshot.wallet_id)
    purchase = CreditPurchase.objects.select_for_update().get(pk=purchase_id)
    validate_payment(purchase, data)
    purchase.provider_reference = data['reference']
    status = data.get('status')
    if status == 'completed':
        # Une réponse ancienne ne réactive jamais un achat déjà signalé remboursé.
        if purchase.status == CreditPurchase.Status.PAID or purchase.paid_at or purchase.refunded_at:
            return purchase
        if purchase.environment == 'live':
            record(wallet, f'purchase:{purchase.pk}', CreditEntry.Kind.PURCHASE,
                   purchase.quantity * UNITS_PER_CREDIT, 0, f'Achat de {purchase.quantity} crédits')
        purchase.status, purchase.paid_at = CreditPurchase.Status.PAID, timezone.now()
        purchase.error_code = ''
    elif status == 'refunded':
        if purchase.paid_at and purchase.environment == 'live':
            wallet.frozen = True  # Des crédits peuvent déjà avoir été consommés : vérification comptable.
            wallet.save(update_fields=['frozen', 'updated_at'])
        purchase.status = CreditPurchase.Status.REVIEW
        purchase.refunded_at = purchase.refunded_at or timezone.now()
    elif purchase.status == CreditPurchase.Status.PAID or purchase.paid_at or purchase.refunded_at:
        return purchase  # Une notification retardée ne défait pas une confirmation.
    elif status in ('failed', 'cancelled', 'expired'):
        purchase.status = CreditPurchase.Status.FAILED
    elif status in ('pending', 'processing'):
        purchase.status = CreditPurchase.Status.PENDING
    else:
        raise ValueError('État de paiement inconnu.')
    purchase.save(update_fields=['provider_reference', 'status', 'paid_at', 'refunded_at', 'error_code'])
    return purchase

