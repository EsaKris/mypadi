from django.shortcuts import render
from django.urls import reverse
from functools import wraps

def tenant_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return render(request, '403.html', {
                'error_message': 'Please login to access this page',
                'login_url': reverse('accounts:login') + f'?next={request.path}'
            }, status=403)
            
        if not hasattr(request.user, 'is_tenant') or not request.user.is_tenant():
            # Show custom 403 template for wrong user type
            return render(request, 'seekers/invalid_role.html',{
                'error_message': 'This page is for property seekers only',
                'register_url': reverse('accounts:register') + f'?user_type=tenant&next={request.path}',
                'required_role': 'tenant',
                'current_role': 'landlord' if hasattr(request.user, 'is_landlord') and request.user.is_landlord() else 'other'
            }, status=403)
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def landlord_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return render(request, '403.html', {
                'error_message': 'Please login to access this page',
                'login_url': reverse('accounts:login') + f'?next={request.path}'
            }, status=403)
            
        if not hasattr(request.user, 'is_landlord') or not (request.user.is_landlord() or request.user.is_admin()):
            return render(request, '403.html', {
                'error_message': 'This page is for landlords only',
                'register_url': reverse('accounts:register') + f'?user_type=landlord&next={request.path}',
                'required_role': 'landlord',
                'current_role': 'tenant' if hasattr(request.user, 'is_tenant') and request.user.is_tenant() else 'other'
            }, status=403)
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view