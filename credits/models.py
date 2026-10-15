from django.utils.translation import gettext_lazy
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

UNITS_PER_CREDIT = 60_000
PRICE_PER_CREDIT_USD = Decimal('0.90')


def credit_amount(units):
    return (Decimal(units) / UNITS_PER_CREDIT).quantize(Decimal('0.01'))


class CreditWallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credit_wallet')
    balance_units = models.PositiveBigIntegerField(default=0)
    reserved_units = models.PositiveBigIntegerField(default=0)
    frozen = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(balance_units__gte=F('reserved_units')), name='wallet_reservations_covered')]

    @property
    def available_units(self):
        return self.balance_units - self.reserved_units

    @property
    def available_credits(self):
        return credit_amount(self.available_units)

    @property
    def reserved_credits(self):
        return credit_amount(self.reserved_units)

    @property
    def balance_credits(self):
        return credit_amount(self.balance_units)


class CreditEntry(models.Model):
    class Kind(models.TextChoices):
        PURCHASE = 'purchase', gettext_lazy('Achat de crédits')
        GRANT = 'grant', gettext_lazy('Ajout de crédits')
        RESERVE = 'reserve', gettext_lazy('Crédits réservés')
        SETTLE = 'settle', gettext_lazy('Doublage facturé')
        RELEASE = 'release', gettext_lazy('Réservation libérée')

    wallet = models.ForeignKey(CreditWallet, on_delete=models.PROTECT, related_name='entries')
    reference = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    balance_delta = models.BigIntegerField(default=0)
    reserved_delta = models.BigIntegerField(default=0)
    balance_after = models.PositiveBigIntegerField()
    reserved_after = models.PositiveBigIntegerField()
    description = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    @property
    def amount(self):
        return credit_amount(abs(self.balance_delta or self.reserved_delta))

    @property
    def balance_after_credits(self):
        return credit_amount(self.balance_after)

    @property
    def display_description(self):
        # Keep accounting records and user-entered video titles unchanged.
        if self.kind == self.Kind.PURCHASE:
            return gettext_lazy('Achat de %(quantity)s crédits') % {'quantity': self.amount}
        if self.description == 'Ajout de crédits':
            return gettext_lazy('Ajout de crédits')
        return self.description


class CreditReservation(models.Model):
    class Status(models.TextChoices):
        HELD = 'held', gettext_lazy('Réservés')
        CAPTURED = 'captured', gettext_lazy('Consommés')
        RELEASED = 'released', gettext_lazy('Libérés')

    job = models.OneToOneField('studio.DubbingJob', on_delete=models.PROTECT, related_name='credit_reservation')
    wallet = models.ForeignKey(CreditWallet, on_delete=models.PROTECT, related_name='reservations')
    per_language_units = models.PositiveBigIntegerField()
    reserved_units = models.PositiveBigIntegerField()
    consumed_units = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.HELD)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(consumed_units__lte=F('reserved_units')), name='reservation_consumption_bounded')]

    @property
    def reserved_credits(self):
        return credit_amount(self.reserved_units)

    @property
    def consumed_credits(self):
        return credit_amount(self.consumed_units)


class CreditPurchase(models.Model):
    class Status(models.TextChoices):
        CREATED = 'created', gettext_lazy('À payer')
        PENDING = 'pending', gettext_lazy('En attente de confirmation')
        PAID = 'paid', gettext_lazy('Payé')
        FAILED = 'failed', gettext_lazy('Paiement non abouti')
        REVIEW = 'review', gettext_lazy('Vérification nécessaire')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(CreditWallet, on_delete=models.PROTECT, related_name='purchases')
    quantity = models.PositiveIntegerField()
    pack = models.CharField(max_length=20, blank=True)
    price_usd = models.DecimalField(max_digits=12, decimal_places=2)
    provider = models.CharField(max_length=30, blank=True)
    environment = models.CharField(max_length=10, default='sandbox')
    provider_reference = models.CharField(max_length=150, unique=True, null=True, blank=True)
    amount_minor = models.PositiveBigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    checkout_url = models.URLField(max_length=600, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    error_code = models.CharField(max_length=40, blank=True)
    quoted_at = models.DateTimeField(null=True, blank=True)
    quoted_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='purchase_positive_quantity')]

    @property
    def payment_amount(self):
        if self.quoted_amount is not None:
            return self.quoted_amount
        if self.amount_minor is None:
            return None
        return Decimal(self.amount_minor) / 100 if self.currency == 'USD' else Decimal(self.amount_minor)


class PaymentWebhook(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', gettext_lazy('À vérifier')
        PROCESSING = 'processing', gettext_lazy('Vérification en cours')
        DONE = 'done', gettext_lazy('Traité')
        REVIEW = 'review', gettext_lazy('Vérification manuelle nécessaire')

    purchase = models.ForeignKey(CreditPurchase, on_delete=models.PROTECT, related_name='webhooks')
    deduplication_key = models.CharField(max_length=220, unique=True)
    event = models.CharField(max_length=40)
    environment = models.CharField(max_length=10)
    payment_reference = models.CharField(max_length=150)
    delivery_id = models.CharField(max_length=200, blank=True)
    payload_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_check_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']
        indexes = [models.Index(fields=['status', 'next_check_at'])]
