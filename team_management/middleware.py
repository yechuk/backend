from django.conf import settings
from django.http import HttpResponse


class ApiCorsMiddleware:
    """Add lightweight CORS handling for API routes without extra dependencies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/') and request.method == 'OPTIONS':
            response = HttpResponse(status=200)
        else:
            response = self.get_response(request)

        if request.path.startswith('/api/'):
            self._apply_cors_headers(request, response)

        return response

    def _apply_cors_headers(self, request, response):
        origin = request.headers.get('Origin')
        allow_all = getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False)
        allowed_origins = set(getattr(settings, 'CORS_ALLOWED_ORIGINS', []))

        if allow_all:
            response['Access-Control-Allow-Origin'] = origin or '*'
            response.setdefault('Vary', 'Origin')
        elif origin and origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
            response.setdefault('Vary', 'Origin')
        else:
            return

        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response['Access-Control-Allow-Headers'] = request.headers.get(
            'Access-Control-Request-Headers',
            'Content-Type',
        )
        response['Access-Control-Max-Age'] = '86400'
