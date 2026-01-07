import os
import sys
import site

# Virtualenv site-packages
site.addsitedir('/home/myhousep/virtualenv/mypadi/3.12/lib/python3.12/site-packages')

# Add project root (folder that contains manage.py)
sys.path.insert(0, '/home/myhousep/mypadi')

# Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mypadi.settings')

# WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
