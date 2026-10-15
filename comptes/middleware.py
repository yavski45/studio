class HtmxRedirectMiddleware:
    """Naviguer après une connexion HTMX au lieu d'insérer la page cible."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.headers.get('HX-Request') == 'true'
            and request.path.startswith('/comptes/')
            and response.status_code in (301, 302, 303)
            and response.has_header('Location')
        ):
            response['HX-Redirect'] = response['Location']
            del response['Location']
            response.status_code = 200
            response.content = b''
        return response
