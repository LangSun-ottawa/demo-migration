import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / '.env')
ASSISTANT_HISTORY_TOKEN = os.getenv('ASSISTANT_HISTORY_TOKEN', 'demo-only-history-service-token')
ASSISTANT_HISTORY_RETENTION_DAYS = 30
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-demo-only-change-me')
DEBUG = os.getenv('DJANGO_DEBUG', 'true').lower() in {'1', 'true', 'yes'}
if not DEBUG and ASSISTANT_HISTORY_TOKEN in {'', 'demo-only-history-service-token'}:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('Set a private ASSISTANT_HISTORY_TOKEN before disabling DEBUG.')
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'DJANGO_CSRF_TRUSTED_ORIGINS',
        'http://127.0.0.1:4200,http://localhost:4200',
    ).split(',')
    if origin.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'demoapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend_config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend_config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'transaction_mode': 'IMMEDIATE', 'timeout': 10},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Vancouver'

USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Local SAML demo: fixed SP/IdP endpoints, never accepted from browser input.
SAML_ENABLED = os.getenv('SAML_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
SAML_SP_BASE_URL = os.getenv('SAML_SP_BASE_URL', 'http://127.0.0.1:8001')
SAML_LOGIN_RETURN_URL = os.getenv('SAML_LOGIN_RETURN_URL', 'http://127.0.0.1:4200/setup')
SAML_IDP_CONFIG_FILE = BASE_DIR.parent / '.local/saml/idp.json'
SAML_GROUP_MAPPING = {
    'demo-readonly': 'feature:demo_setup:readonly',
    'demo-readwrite': 'feature:demo_setup:readwrite',
}
