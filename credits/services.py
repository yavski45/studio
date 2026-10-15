"""Écritures atomiques du portefeuille ; montants exacts, sans nombres flottants."""
from django.utils.translation import gettext_lazy
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from django.db import transaction
from django.utils import timezone

from .models import CreditEntry, CreditReservation, CreditWallet, UNITS_PER_CREDIT


class InsufficientCredits(Exception):
    pass


def wallet_for(user):
    return CreditWallet.objects.get_or_create(user=user)[0]


def metered_units(duration_ms, rounding):
    if duration_ms <= 0:
        raise ValueError('Durée invalide.')
    if rounding == 'minute':
        return ((duration_ms + UNITS_PER_CREDIT - 1) // UNITS_PER_CREDIT) * UNITS_PER_CREDIT
    if rounding == 'prorata':
        return duration_ms
    raise ValueError('Règle de facturation inconnue.')


def milliseconds(seconds):
    try:
        value = Decimal(str(seconds))
    except InvalidOperation:
        raise ValueError('Durée invalide.') from None
    if not value.is_finite() or value <= 0:
        raise ValueError('Durée invalide.')
    return int((value * 1000).to_integral_value(rounding=ROUND_CEILING))


def record(wallet, reference, kind, balance_delta, reserved_delta, description):
    wallet.balance_units += balance_delta
    wallet.reserved_units += reserved_delta
    if wallet.balance_units < wallet.reserved_units or wallet.reserved_units < 0:
        raise InsufficientCredits
    wallet.save(update_fields=['balance_units', 'reserved_units', 'updated_at'])
    return CreditEntry.objects.create(wallet=wallet, reference=reference, kind=kind,
        balance_delta=balance_delta, reserved_delta=reserved_delta,
        balance_after=wallet.balance_units, reserved_after=wallet.reserved_units,
        description=description[:250])


@transaction.atomic
def grant_credits(user, credits, reference, description=gettext_lazy('Ajout de crédits')):
    amount = Decimal(str(credits)) * UNITS_PER_CREDIT
    if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
        raise ValueError('Montant de crédits invalide.')
    wallet = wallet_for(user)
    wallet = CreditWallet.objects.select_for_update().get(pk=wallet.pk)
    existing = CreditEntry.objects.filter(reference=reference).first()
    if existing:
        if existing.wallet_id != wallet.pk or existing.balance_delta != int(amount) or existing.kind != CreditEntry.Kind.GRANT:
            raise ValueError('Référence déjà utilisée pour une autre écriture.')
        return existing
    return record(wallet, reference, CreditEntry.Kind.GRANT, int(amount), 0, description)


@transaction.atomic
def reserve_job(job, duration_ms, rounding):
    wallet = wallet_for(job.user)
    wallet = CreditWallet.objects.select_for_update().get(pk=wallet.pk)
    existing = CreditReservation.objects.filter(job=job).first()
    if existing:
        if existing.wallet_id != wallet.pk or existing.status != CreditReservation.Status.HELD:
            raise ValueError('Réservation incompatible avec un nouvel envoi.')
        return existing
    count = len(set(job.target_locales))
    if not count:
        raise ValueError('Aucune langue demandée.')
    per_language = metered_units(duration_ms, rounding)
    total = per_language * count
    if wallet.frozen or wallet.available_units < total:
        raise InsufficientCredits
    reservation = CreditReservation.objects.create(job=job, wallet=wallet,
        per_language_units=per_language, reserved_units=total)
    record(wallet, f'reserve:{job.pk}', CreditEntry.Kind.RESERVE, 0, total, job.title)
    return reservation


@transaction.atomic
def settle_job(job, successful_locales):
    reservation = CreditReservation.objects.filter(job=job).first()
    if not reservation:
        return None  # Travaux antérieurs à l’activation du portefeuille.
    wallet = CreditWallet.objects.select_for_update().get(pk=reservation.wallet_id)
    reservation = CreditReservation.objects.select_for_update().get(pk=reservation.pk)
    if reservation.status != CreditReservation.Status.HELD:
        return reservation
    succeeded = set(successful_locales) & set(job.target_locales)
    consumed = reservation.per_language_units * len(succeeded)
    if consumed > reservation.reserved_units:
        raise ValueError('Consommation incohérente.')
    record(wallet, f'settle:{job.pk}', CreditEntry.Kind.SETTLE if consumed else CreditEntry.Kind.RELEASE,
        -consumed, -reservation.reserved_units, job.title)
    reservation.consumed_units = consumed
    reservation.status = CreditReservation.Status.CAPTURED if consumed else CreditReservation.Status.RELEASED
    reservation.settled_at = timezone.now()
    reservation.save(update_fields=['consumed_units', 'status', 'settled_at'])
    return reservation
