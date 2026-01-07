# landlords/backends.py
from django.contrib.auth.backends import ModelBackend

class AdminAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username, password, **kwargs)
        if user and user.is_staff:
            return user
        return None