from django.conf import settings

from .errors import error_html


class FriendlyNotFoundMiddleware:
    """Show the public 404 screen even while developing with DEBUG enabled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            settings.DEBUG
            and response.status_code == 404
            and not response.streaming
            and response.get('Content-Type', '').split(';')[0].strip() == 'text/html'
        ):
            response.content = error_html(404)
            response['Cache-Control'] = 'no-store'
            if response.has_header('Content-Length'):
                response['Content-Length'] = str(len(response.content))
        return response
