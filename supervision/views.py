from django.utils.translation import gettext_lazy
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.shortcuts import redirect
from kombu.exceptions import OperationalError
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from credits.models import CreditPurchase
from .forms import ReportForm
from .models import DailyVisit
from .murf_alerts import alert_context
from .tasks import refresh_murf_credits


def line_points(values):
    maximum = max(values) or 1
    return ' '.join(f'{16 + i * 608 / max(len(values) - 1, 1):.2f},{164 - float(value / maximum) * 136:.2f}'
                    for i, value in enumerate(values))


@never_cache
@login_required
@require_GET
def dashboard(request):
    if not request.user.is_active or not request.user.is_staff:
        raise PermissionDenied
    params = {'period': '30', 'currency': 'USD', **request.GET.dict()}
    form = ReportForm(params)
    valid = form.is_valid()
    days = int(form.cleaned_data.get('period', '30'))
    currency = form.cleaned_data.get('currency', 'USD') if valid else 'USD'
    rate = form.cleaned_data.get('rate') if valid else None
    factor = rate if currency == 'XOF' else Decimal(1)
    today = timezone.localdate()
    first = today - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(first, time.min))
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
    live = CreditPurchase.objects.filter(environment='live', paid_at__isnull=False)
    purchases = live.filter(paid_at__gte=start, paid_at__lt=end)
    refunds = live.filter(refunded_at__gte=start, refunded_at__lt=end)
    gross = purchases.aggregate(total=Sum('price_usd'))['total'] or Decimal(0)
    refunded = refunds.aggregate(total=Sum('price_usd'))['total'] or Decimal(0)
    visits = DailyVisit.objects.filter(day__gte=first, day__lte=today)
    daily_visits = {row['day']: row for row in visits.values('day').annotate(
        visitors=Count('visitor_hash', distinct=True), views=Sum('page_views'))}
    daily_income = {row['date']: row['total'] for row in purchases.annotate(date=TruncDate('paid_at')).values('date').annotate(total=Sum('price_usd'))}
    daily_refunds = {row['date']: row['total'] for row in refunds.annotate(date=TruncDate('refunded_at')).values('date').annotate(total=Sum('price_usd'))}
    rows = []
    for index in range(days):
        day = first + timedelta(days=index)
        visit = daily_visits.get(day, {})
        rows.append({'day': day, 'visitors': visit.get('visitors', 0), 'views': visit.get('views', 0),
                     'revenue': daily_income.get(day, Decimal(0)) * factor,
                     'refunds': daily_refunds.get(day, Decimal(0)) * factor})
    metrics = [
        {'label': 'Visiteurs uniques', 'value': visits.values('visitor_hash').distinct().count(), 'money': False},
        {'label': gettext_lazy('Pages vues'), 'value': visits.aggregate(total=Sum('page_views'))['total'] or 0, 'money': False},
        {'label': gettext_lazy('Recettes brutes'), 'value': gross * factor, 'money': True},
        {'label': gettext_lazy('Recettes après remboursements'), 'value': (gross - refunded) * factor, 'money': True},
    ]
    context = {'murf': alert_context(), 'form': form, 'metrics': metrics, 'currency': currency, 'unit': '$' if currency == 'USD' else 'FCFA',
        'rate': rate, 'first': first, 'today': today, 'days': days, 'rows': rows,
        'visitor_points': line_points([Decimal(row['visitors']) for row in rows]),
        'income_points': line_points([row['revenue'] for row in rows]),
        'visitor_max': max(row['visitors'] for row in rows),
        'income_max': max(row['revenue'] for row in rows),
        'payment_count': purchases.count(), 'refunded': refunded * factor,
        'credits_sold': purchases.aggregate(total=Sum('quantity'))['total'] or 0,
        'purchases': purchases.order_by('-paid_at')[:20],
        'tracking_started': DailyVisit.objects.order_by('day').values_list('day', flat=True).first(),
        'updated_at': timezone.now()}
    template = 'supervision/_report.html' if request.headers.get('HX-Request') == 'true' else 'supervision/dashboard.html'
    return render(request, template, context)


@never_cache
@login_required
@require_GET
def murf_alert(request):
    if not request.user.is_active or not request.user.is_staff:
        raise PermissionDenied
    return render(request, 'supervision/_murf_alert.html', {'murf': alert_context()})


@never_cache
@login_required
@require_POST
def refresh_murf(request):
    if not request.user.is_active or not request.user.is_staff:
        raise PermissionDenied
    queued = True
    try:
        refresh_murf_credits.delay()
    except (OperationalError, OSError):
        queued = False
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'supervision/_murf_alert.html',
                      {'murf': alert_context(), 'refresh_requested': True, 'refresh_queued': queued})
    return redirect('supervision:dashboard')
