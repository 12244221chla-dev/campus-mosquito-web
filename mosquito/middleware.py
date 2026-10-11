class FrameOptionsMiddleware:
    """Restore a restrictive frame policy after SimpleUI adjusts Django middleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Frame-Options"] = "DENY"
        return response
