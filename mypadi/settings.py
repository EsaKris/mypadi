"""
Django settings for mypadi project - PRODUCTION READY
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import pymysql

# MySQL compatibility
pymysql.install_as_MySQLdb()

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = False  # Production must have DEBUG=False
ALLOWED_HOSTS = [
    'myhousepadi.com',
    'www.myhousepadi.com',
    'myhousepadi.name.ng',
    'https://myhousepadii.onrender.com',
    '127.0.0.1',
    '127.0.0.1:8000',
    'localhost',
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.humanize",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "landing",
    "seekers",
    "core",
    "landlords",
    "rest_framework",
    "corsheaders",
    "allauth",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "accounts.middleware.RoleAccessMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "landlords.middleware.AdminAreaMiddleware",
]

ROOT_URLCONF = "mypadi.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / 'templates'],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mypadi.wsgi.application"

# Database - Production MySQL
DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': os.environ.get('DB_NAME'),
#         'USER': os.environ.get('DB_USER'),
#         'PASSWORD': os.environ.get('DB_PASSWORD'),
#         'HOST': os.environ.get('DB_HOST', 'localhost'),
#         'PORT': os.environ.get('DB_PORT', '3306'),
#         'OPTIONS': {'charset': 'utf8mb4'},
#     }
# }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv('TIME_ZONE', 'Africa/Lagos')
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / "media"

# Logging
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': LOGS_DIR / 'django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Authentication
AUTHENTICATION_BACKENDS = [
    'landlords.backends.AdminAuthBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Login / Logout
LOGIN_URL = 'admin_login'
USER_LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'landlords_admin:admin_dashboard'
USER_LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

# Admin-specific
ADMIN_LOGIN_REDIRECT_URL = 'landlords_admin:admin_dashboard'
ADMIN_LOGOUT_REDIRECT_URL = 'landlords_admin:admin_login'

# Email settings (Gmail SMTP)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'myhousepadi@gmail.com')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# Security
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [
    'https://myhousepadi.com',
    'https://www.myhousepadi.com',
    'https://myhousepadi.name.ng',
    'https://myhousepadii.onrender.com'
]

# Custom error handlers
handler403 = 'accounts.views.custom_permission_denied_view'

# Encryption key for sensitive data
ENCRYPTION_KEY = os.environ['ENCRYPTION_KEY']

LIVE_DOMAINS = {
    'primary': 'https://myhousepadi.com',
    'secondary': 'https://myhousepadii.onrender.com',
}

# Production site URL (used for emails / links)
SITE_URL = "https://myhousepadi.com"
