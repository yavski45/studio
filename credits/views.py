from django.utils.translation import gettext_lazy
import logging
import hashlib
import uuid
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured, RequestDataTooBig
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from studio.views import verified_view 
from .forms import PurchaseForm
from .config import payment_environment
from .catalog import PACKS
from .geniuspay import InvalidWebhookSignature, PaymentUnavailable, configured, create_payment, get_payment, webhook_payload
from .models import CreditPurchase, PaymentWebhook, PRICE_PER_CREDIT_USD
from .payments import PaymentMismatch, apply_payment, bind_checkout_quote, validate_reference, validate_payment
from .services import wallet_for

logger = logging.getLogger(__name__)


def purchase_details(pk):
    return redirect(reverse('credits:purchase', args=[pk]) + '?details=1')


def wallet_context(request, form=None):
    wallet = wallet_for(request.user)
    selected = (form['pack'].value() if form else request.GET.get('pack', 'starter'))
    selected = selected if selected in PACKS else 'starter'
    offers = [{'key': key, **offer, 'unit_usd': (offer['usd'] / offer['quantity']).quantize(Decimal('0.01'))} for key, offer in PACKS.items()]
    return {'wallet': wallet, 'entries': wallet.entries.all()[:50], 'purchases': wallet.purchases.all()[:20],
            'form': form or PurchaseForm(initial={'pack': selected}), 'price_usd': PRICE_PER_CREDIT_USD,
            'payment_ready': configured(), 'offers': offers, 'selected_pack': selected,
            'pack_totals': {key: str(offer['usd']) for key, offer in PACKS.items()},
            'pack_quantities': {key: offer['quantity'] for key, offer in PACKS.items()},
            'selected_offer': PACKS[selected],
            'sandbox': payment_environment() == 'sandbox'}


@verified_view
@require_GET
def wallet(request):
    return render(request, 'credits/wallet.html', wallet_context(request))


@verified_view
@require_POST
def buy(request):
    form = PurchaseForm(request.POST)
    if form.is_valid():
        if not configured():
            form.add_error(None, gettext_lazy('La recharge sera disponible dès que le paiement sera configuré.'))
        elif wallet_for(request.user).frozen:
            form.add_error(None, gettext_lazy('Votre portefeuille nécessite une vérification. Contactez l’équipe Dublao.'))
        else:
            offer = PACKS[form.cleaned_data['pack']]
            with transaction.atomic():
                purchase, created = CreditPurchase.objects.get_or_create(pk=form.cleaned_data['submission_id'], defaults={
                    'wallet': wallet_for(request.user), 'quantity': offer['quantity'], 'pack': form.cleaned_data['pack'],
                    'price_usd': offer['usd'],
                    'amount_minor': int(offer['usd'] * 100), 'currency': 'USD',
                    'provider': 'geniuspay', 'environment': payment_environment(),
                    'status': CreditPurchase.Status.PENDING,
                })
                if purchase.wallet.user_id != request.user.pk:
                    return JsonResponse({'error': 'Achat introuvable.'}, status=404)
            if not created:
                if purchase.environment != payment_environment():
                    messages.warning(request, gettext_lazy('Cet achat appartient à un autre mode de paiement. Choisissez un pack pour créer une nouvelle tentative.'))
                    return redirect('credits:wallet')
                if purchase.status == 'pending' and purchase.checkout_url:
                    return redirect(purchase.checkout_url)
                return purchase_details(purchase.pk)
            try:
                return_path = reverse('credits:callback') + '?purchase=' + str(purchase.pk)
                data, url = create_payment(purchase, return_path)
                # Le webhook peut avoir été traité pendant l’appel réseau.
                with transaction.atomic():
                    saved = CreditPurchase.objects.select_for_update().get(pk=purchase.pk)
                    validate_reference(saved, data)
                    saved.provider_reference = data['reference']
                    saved.save(update_fields=['provider_reference'])
                metadata = data.get('metadata')
                if (not isinstance(metadata, dict) or not {'order_id', 'user_id'} <= metadata.keys()
                        or 'currency' not in data or 'environment' not in data):
                    data = get_payment(data['reference'])
                # Seule la réponse authentifiée de création fixe la conversion.
                # Le webhook et les GET ultérieurs ne changent jamais ce montant.
                with transaction.atomic():
                    saved = CreditPurchase.objects.select_for_update().get(pk=purchase.pk)
                    bind_checkout_quote(saved, data)
                    saved.checkout_url, saved.error_code = url, ''
                    saved.save(update_fields=['currency', 'amount_minor', 'quoted_amount', 'quoted_at', 'checkout_url', 'error_code'])
                return redirect(url)
            except PaymentUnavailable as error:
                status = 'failed' if error.http_status in (401, 403, 422) else 'review'
                code = error.provider_code or ('API_REJECTED' if status == 'failed' else 'PROVIDER_UNAVAILABLE')
                CreditPurchase.objects.filter(pk=purchase.pk, paid_at__isnull=True).update(status=status, error_code=code)
                logger.warning('Initialisation Genius Pay non confirmée ; achat %s ; HTTP %s ; code %s ; champs %s.',
                               purchase.pk, error.http_status, error.provider_code or 'NON_PRECISE',
                               ','.join(error.rejected_fields) or 'NON_PRECISES')
                return purchase_details(purchase.pk)
            except (ImproperlyConfigured, ValueError, IntegrityError) as error:
                code = (error.code if isinstance(error, PaymentMismatch) else
                        'CONFIGURATION_MISSING' if isinstance(error, ImproperlyConfigured) else 'PAYMENT_MISMATCH')
                CreditPurchase.objects.filter(pk=purchase.pk, paid_at__isnull=True).update(status='review', error_code=code)
                logger.warning('Réponse checkout incohérente ou configuration absente ; achat %s ; code %s.', purchase.pk, code)
                return purchase_details(purchase.pk)
    return render(request, 'credits/wallet.html', wallet_context(request, form), status=400)


@verified_view
@require_GET
def purchase(request, pk):
    order = get_object_or_404(CreditPurchase, pk=pk, wallet__user=request.user)
    # Les anciens checkouts utilisent cette URL comme retour marchand.
    # Les liens de l'historique demandent explicitement la fiche détaillée.
    if request.GET.get('details') != '1':
        return finish_payment_return(request, order)
    return render(request, 'credits/purchase.html', {'purchase': order,
        'payment_mode_matches': order.environment == payment_environment()})


@verified_view
@require_POST
def verify(request, pk):
    order = get_object_or_404(CreditPurchase, pk=pk, wallet__user=request.user)
    if order.environment != payment_environment():
        return redirect('credits:wallet')
    refresh_payment(order)
    if request.headers.get('HX-Request') == 'true':
        response = render(request, 'credits/_purchase_status.html', {'purchase': order, 'payment_mode_matches': True})
        if order.status in ('paid', 'failed'):
            response['HX-Redirect'] = reverse('credits:wallet')
        return response
    if order.status in ('paid', 'failed'):
        return redirect('credits:wallet')
    return purchase_details(order.pk)


def refresh_payment(order):
    if order.environment == payment_environment() and order.provider_reference and order.status != 'paid':
        try:
            apply_payment(order.pk, get_payment(order.provider_reference))
        except (PaymentUnavailable, ImproperlyConfigured, ValueError):
            logger.warning('Confirmation Genius Pay différée ; achat %s.', order.pk)
    order.refresh_from_db()


@verified_view
@require_GET
def payment_callback(request):
    purchase_id = request.GET.get('purchase')
    if not purchase_id:
        return redirect('credits:wallet')
    try:
        pk = uuid.UUID(purchase_id)
    except (ValueError, AttributeError):
        return redirect('credits:wallet')
    order = get_object_or_404(CreditPurchase, pk=pk, wallet__user=request.user)
    return finish_payment_return(request, order)


@verified_view
@require_GET
def payment_return(request, pk):
    order = get_object_or_404(CreditPurchase, pk=pk, wallet__user=request.user)
    return finish_payment_return(request, order)


def finish_payment_return(request, order):
    # L'URL de retour ne prouve jamais le paiement, même avec status=completed.
    refresh_payment(order)
    if order.status == 'paid':
        if order.environment == 'sandbox':
            messages.info(request, gettext_lazy('Paiement de test confirmé. Aucun crédit utilisable n’a été ajouté.'))
        else:
            messages.success(request, gettext_lazy('Paiement confirmé. Vos crédits sont disponibles dans votre portefeuille.'))
    elif order.status == 'failed':
        messages.info(request, gettext_lazy('Le paiement a été annulé ou n’a pas abouti. Vous pouvez choisir un pack pour réessayer.'))
    elif order.status == 'review':
        messages.warning(request, gettext_lazy('Cette tentative nécessite une vérification. Consultez cet achat dans votre historique.'))
    else:
        messages.info(request, gettext_lazy('Retour au portefeuille. Le paiement n’est pas encore confirmé ; vous pouvez le reprendre depuis votre historique.'))
    return redirect('credits:wallet')


@csrf_exempt
@require_POST
def webhook(request):
    try:
        if request.content_type != 'application/json':
            raise ValueError('JSON requis.')
        signature = request.headers.get('X-Webhook-Signature', '')
        timestamp = request.headers.get('X-Webhook-Timestamp', '')
        event = request.headers.get('X-Webhook-Event', '')
        if not signature or not timestamp or not event:
            raise ValueError('En-tête obligatoire manquant.')
        body = request.body
        if len(body) > 65536:
            raise RequestDataTooBig
        payload = webhook_payload(body, signature, timestamp)
        if event != payload.get('event'):
            raise ValueError('Événement incohérent.')
        if (payload.get('environment') != payment_environment()
                or request.headers.get('X-Webhook-Environment', '') not in ('', payload.get('environment'))):
            raise ValueError('Environnement incorrect.')
        if event == 'webhook.test':
            logger.info('Test webhook Genius Pay validé (%s).', payload['environment'])
            return JsonResponse({'success': True})
        if event not in {'payment.initiated', 'payment.success', 'payment.failed',
                         'payment.cancelled', 'payment.expired', 'payment.refunded'}:
            return JsonResponse({'success': True})
        # Le guide place l’environnement dans l’enveloppe, pas dans data.
        data = {**payload['data'], 'environment': payload['environment']}
        if payload['data'].get('environment', payload['environment']) != payload['environment']:
            raise ValueError('Environnement incohérent.')
        order_id = uuid.UUID(str((data.get('metadata') or {}).get('order_id')))
        order = CreditPurchase.objects.filter(pk=order_id, provider='geniuspay').first()
        if not order:
            return JsonResponse({'success': True})
        reference = data.get('reference')
        if not isinstance(reference, str) or not 0 < len(reference) <= 150:
            raise ValueError('Référence incorrecte.')
        validate_payment(order, data)
        digest = hashlib.sha256(body).hexdigest()
        event_id = payload.get('id')
        if event_id is not None and (not isinstance(event_id, str) or not 0 < len(event_id) <= 200):
            raise ValueError('Identifiant incorrect.')
        delivery_id = request.headers.get('X-Webhook-Delivery', '')
        if len(delivery_id) > 200:
            raise ValueError('Identifiant de livraison incorrect.')
        with transaction.atomic():
            receipt, created = PaymentWebhook.objects.get_or_create(
                deduplication_key=payload['environment'] + ':' + (event_id or digest),
                defaults={'purchase': order, 'event': event, 'environment': payload['environment'],
                          'payment_reference': reference, 'payload_digest': digest, 'delivery_id': delivery_id})
            if (receipt.purchase_id != order.pk or receipt.event != event
                    or receipt.payment_reference != reference):
                raise ValueError('Identifiant déjà utilisé pour une autre notification.')
            # Beat publie les notifications persistées ; aucune requête réseau
            # (API ou Redis) ne retarde la réponse HTTP.
        logger.info('Notification Genius Pay reçue : %s (%s), doublon=%s.', receipt.pk, event, not created)
    except RequestDataTooBig:
        return JsonResponse({'error': 'Notification trop grande.'}, status=413)
    except ImproperlyConfigured:
        return JsonResponse({'error': 'Paiement indisponible.'}, status=503)
    except InvalidWebhookSignature:
        return JsonResponse({'error': 'Signature incorrecte.'}, status=401)
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Notification incorrecte.'}, status=400)
    return JsonResponse({'success': True})

