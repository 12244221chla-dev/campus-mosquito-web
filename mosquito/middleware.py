class FrameOptionsMiddleware:
    """Allow SimpleUI's same-origin admin frames; deny framing elsewhere."""


    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Frame-Options"] = (
            "SAMEORIGIN" if request.path.startswith("/admin/") else "DENY"
        )
        return response
