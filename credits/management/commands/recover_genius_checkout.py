from urllib.parse import quote

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from credits.geniuspay import PaymentUnavailable, get_payment, safe_checkout_url
from credits.models import CreditPurchase
from credits.payments import bind_checkout_quote


class Command(BaseCommand):
    help = 'Rouvre une tentative non payée rejetée par le contrôle de montant, sans créer de transaction ni crédit.'

    def add_arguments(self, parser):
        parser.add_argument('purchase_id')

    def handle(self, *args, **options):
        order = CreditPurchase.objects.filter(pk=options['purchase_id'], provider='geniuspay',
            status='review', error_code='PAYMENT_AMOUNT_MISMATCH', quoted_at__isnull=True,
            paid_at__isnull=True, refunded_at__isnull=True, provider_reference__isnull=False).first()
        if not order:
            raise CommandError('Tentative non disponible pour cette récupération.')
        try:
            data = get_payment(order.provider_reference)
            if data.get('status') != 'pending':
                raise CommandError('La transaction n’est plus en attente de paiement ; aucune modification effectuée.')
            # Le chemin canonique du checkout est documenté par Genius Pay.
            url = safe_checkout_url(data.get('checkout_url') or order.checkout_url or
                'https://geniuspay.ci/checkout/' + quote(order.provider_reference, safe=''))
            with transaction.atomic():
                saved = CreditPurchase.objects.select_for_update().get(pk=order.pk)
                if (saved.status != 'review' or saved.quoted_at or saved.paid_at or saved.refunded_at
                        or saved.provider_reference != order.provider_reference):
                    raise CommandError('Cette tentative a changé ; aucune modification effectuée.')
                bind_checkout_quote(saved, data)
                saved.status, saved.error_code, saved.checkout_url = 'pending', '', url
                saved.save(update_fields=['currency', 'amount_minor', 'quoted_amount', 'quoted_at',
                                         'status', 'error_code', 'checkout_url'])
        except (PaymentUnavailable, ValueError):
            raise CommandError('Les informations du paiement n’ont pas pu être confirmées ; aucune modification effectuée.') from None
        self.stdout.write(self.style.SUCCESS(f'Tentative récupérée : {saved.payment_amount} {saved.currency}. Aucun paiement créé ni crédit ajouté.'))
        self.stdout.write(f'/credits/achats/{saved.pk}/?details=1')
