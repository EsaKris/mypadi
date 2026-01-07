# landlords/middleware.py
from django.shortcuts import redirect

class AdminAreaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip middleware for login page and static files
        if (request.path.startswith('/admin/') and 
            not request.path.startswith('/admin/login/') and 
            not request.user.is_staff):
            return redirect('landlords_admin:login')
        return self.get_response(request)