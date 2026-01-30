"""
URL configuration for mypadi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.http import FileResponse
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from pathlib import Path

from landlords.admin_views import AdminLoginView 

def google_verification(request):
    path = Path(__file__).resolve().parent.parent / "verification/google5f2380d4436b4f7d.html"
    return FileResponse(open(path, 'rb'), content_type='text/html')

urlpatterns = [

    path('google5f2380d4436b4f7d.html', google_verification, name='google_verification'),
    path('admin/', include(('landlords.urls_admin', 'landlords_admin'))),
    path('django-admin/', admin.site.urls),

    path('', include(('landing.urls', 'landing'), namespace='landing')),
    path('auth/', include(('accounts.urls', 'accounts'), namespace='accounts')), 
    path('seekers/', include(('seekers.urls', 'seekers'), namespace='seekers')),
    path('landlords/', include('landlords.urls', namespace='landlords')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
