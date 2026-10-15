"""Error screens that do not require the database or external services."""
from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET


ERRORS = {
    400: (gettext_lazy('Cette demande ne peut pas aboutir.'), gettext_lazy('Revenez à l’accueil, puis recommencez votre navigation.')),
    403: (gettext_lazy('Cet accès n’est pas autorisé.'), gettext_lazy('Votre compte ne permet pas d’accéder à cette page. Revenez à votre espace pour continuer.')),
    404: (gettext_lazy('Cette page est introuvable.'), gettext_lazy('Le lien a peut-être changé, ou la page n’existe plus. Votre prochaine vidéo vous attend dans le studio.')),
    500: (gettext_lazy('Un problème nous interrompt.'), gettext_lazy('Nous ne pouvons pas afficher cette page pour le moment. Réessayez un peu plus tard.')),
    502: (gettext_lazy('Le studio est momentanément indisponible.'), gettext_lazy('La connexion avec le service n’a pas abouti. Réessayez dans quelques instants.')),
    503: (gettext_lazy('Le studio est momentanément indisponible.'), gettext_lazy('Le service ne peut pas répondre pour le moment. Réessayez dans quelques instants.')),
    504: (gettext_lazy('Le service met trop de temps à répondre.'), gettext_lazy('La demande n’a pas abouti à temps. Réessayez dans quelques instants.')),
}


def error_html(code):
    title, message = ERRORS[code]
    # No RequestContext: authentication and session lookups can fail during a 500.
    return render_to_string('errors/page.html', {'code': code, 'error_title': title, 'error_message': message})


def error_response(code):
    response = HttpResponse(error_html(code), status=code)
    response['Cache-Control'] = 'no-store'
    return response


def bad_request(request, exception):
    return error_response(400)


def permission_denied(request, exception):
    return error_response(403)


def page_not_found(request, exception):
    return error_response(404)


def server_error(request):
    return error_response(500)


def csrf_failure(request, reason=''):
    return error_response(403)


@require_GET
def preview(request, code):
    if code not in ERRORS:
        raise Http404
    return error_response(code)
