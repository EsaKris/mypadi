# from django.http import HttpResponse

# class MaintenanceModeMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         ALLOWED_PATHS = [
#             "/admin/",  # allow Django admin if needed
#         ]

#         # Allow admin, static, and media
#         if (
#             any(request.path.startswith(p) for p in ALLOWED_PATHS)
#             or request.path.startswith("/static/")
#             or request.path.startswith("/media/")
#         ):
#             return self.get_response(request)

#         return HttpResponse(
#             "Site under maintenance. Please check back later.",
#             status=503
#         )
