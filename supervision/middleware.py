from django.utils.translation import gettext_lazy
import logging
import uuid

from django.db import DatabaseError
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import DailyVisit

logger = logging.getLogger(__name__)
COOKIE = 'dublao_visitor'
SALT = 'supervision.visitor'


class VisitorMiddleware:
    """Mesure les pages HTML, sans stocker IP, email, URL ni agent utilisateur."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.method != 'GET' or response.status_code != 200
                or 'text/html' not in response.get('Content-Type', '')
                or request.headers.get('HX-Request') == 'true'
                or getattr(request.user, 'is_staff', False)
                or request.path.startswith(('/admin/', '/administration/', '/static/', '/media/',
                                             '/credits/callback/', '/credits/retour/'))
                or any(token in request.headers.get('User-Agent', '').lower()
                       for token in ('bot', 'crawler', 'spider'))):
            return response
        visitor = request.get_signed_cookie(COOKIE, default='', salt=SALT, max_age=31536000)
        try:
            visitor = str(uuid.UUID(visitor))
        except (ValueError, AttributeError):
            visitor = str(uuid.uuid4())
        digest = salted_hmac(SALT, visitor).hexdigest()
        try:
            row, created = DailyVisit.objects.get_or_create(day=timezone.localdate(), visitor_hash=digest)
            if not created:
                DailyVisit.objects.filter(pk=row.pk).update(page_views=F('page_views') + 1)
        except DatabaseError:
            logger.warning(gettext_lazy('Statistiques de visites momentanément indisponibles.'))
            return response
        if not request.COOKIES.get(COOKIE) or request.get_signed_cookie(COOKIE, default='', salt=SALT) != visitor:
            response.set_signed_cookie(COOKIE, visitor, salt=SALT, max_age=31536000,
                                       httponly=True, secure=request.is_secure(), samesite='Lax')
        return response
