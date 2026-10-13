class FrameOptionsMiddleware:
    """Restore a restrictive frame policy after SimpleUI adjusts Django middleware.

    默认仍是 DENY（生产姿态）；云端演示环境需要被预览窗口以 iframe 嵌入时，
    可用 DJANGO_FRAME_OPTIONS=ALLOWALL 去掉该响应头。
    """


    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Frame-Options"] = "DENY"
        return response
