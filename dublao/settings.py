from pathlib import Path
import os
import sys

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# Le rechargement de runserver hérite des anciennes variables du parent.
# En développement, .env doit remplacer ces valeurs ; Docker conserve ses variables.
load_dotenv(BASE_DIR / '.env', override='runserver' in sys.argv)


def env_bool(name, default=False):
    value = os.getenv(name, str(default)).strip().lower()
    if value not in {'true', 'false', '1', '0'}:
        raise ImproperlyConfigured(f'{name} doit valoir true, false, 1 ou 0.')
    return value in {'true', '1'}


def env_list(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool('DEBUG', default=True)

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
CSRF_FAILURE_VIEW = 'dublao.errors.csrf_failure'
SITE_PUBLIC_URL = os.getenv('SITE_PUBLIC_URL', '').strip()
SEO_INDEXING_ENABLED = env_bool('SEO_INDEXING_ENABLED', default=False)

 
# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',
    'comptes.apps.ComptesConfig',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'landing', 
    'studio', 
    'credits',
    'supervision',
    'wallet', 
    'payment',
]
  
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'dublao.seo.IndexingMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'dublao.middleware.FriendlyNotFoundMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'supervision.middleware.VisitorMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'comptes.middleware.HtmxRedirectMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'dublao.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'dublao' / 'templates'],
        'APP_DIRS': True, 
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'dublao.seo.context',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dublao.wsgi.application'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = 'espace_compte'
ACCOUNT_LOGOUT_REDIRECT_URL = 'landing:home'
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_FORMS = {
    'signup': 'comptes.forms.SignupForm',
    'login': 'comptes.forms.LoginForm',
    'reset_password': 'comptes.forms.ResetPasswordForm',
    'reset_password_from_key': 'comptes.forms.ResetPasswordKeyForm',
}
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    },
}
if GOOGLE_OAUTH_ENABLED:
    SOCIALACCOUNT_PROVIDERS['google']['APP'] = {
        'client_id': GOOGLE_OAUTH_CLIENT_ID,
        'secret': GOOGLE_OAUTH_CLIENT_SECRET,
        'key': '',
    }


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB'),
        'USER': os.getenv('POSTGRES_USER'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('POSTGRES_HOST'),
        'PORT': os.getenv('POSTGRES_PORT'), 
        'CONN_MAX_AGE': 60,
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 5,
            'sslmode': os.getenv('POSTGRES_SSLMODE', 'prefer'),
        },
    }
}
 

# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'fr'
LANGUAGES = [('fr', 'Français'), ('en', 'English')]
LOCALE_PATHS = [BASE_DIR / 'locale']
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = 'Lax'
LANGUAGE_COOKIE_HTTPONLY = True
LANGUAGE_COOKIE_SECURE = not DEBUG

TIME_ZONE = 'Africa/Abidjan'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Les vidéos et sous-titres sont privés dans R2. Les fichiers statiques
# restent séparés et seront servis par l'hébergement de l'application.
R2_ACCOUNT_ID = os.getenv('R2_ACCOUNT_ID', '')
R2_ENDPOINT_URL = os.getenv(
    'R2_ENDPOINT_URL',
    f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com' if R2_ACCOUNT_ID else '',
)
STORAGES = {
    'default': {
        'BACKEND': 'dublao.storage.PrivateR2Storage',
        'OPTIONS': {
            'access_key': os.getenv('R2_ACCESS_KEY_ID'),
            'secret_key': os.getenv('R2_SECRET_ACCESS_KEY'),
            'bucket_name': os.getenv('R2_BUCKET_NAME'),
            'endpoint_url': R2_ENDPOINT_URL,
            'region_name': 'auto',
            'signature_version': 's3v4',
            'addressing_style': 'path',
            'default_acl': None,
            'querystring_auth': True,
            'querystring_expire': 3600,
            'custom_domain': None,
            'file_overwrite': False,
            'max_memory_size': 5 * 1024 * 1024,
        }, 
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# Murf Dub : travaux temporaires identifiés par job_id, sans project_id.
MURFDUB_API_KEY = os.getenv('MURFDUB_API_KEY', '')
MURFDUB_ENABLED = env_bool('MURFDUB_ENABLED', default=bool(MURFDUB_API_KEY))
# 0 désactive le plafond de taille applicatif pour les vidéos.
STUDIO_MAX_UPLOAD_BYTES = int(os.getenv('STUDIO_MAX_UPLOAD_BYTES', '0'))
STUDIO_MAX_ACTIVE_JOBS = int(os.getenv('STUDIO_MAX_ACTIVE_JOBS', '3'))
STUDIO_DOWNLOAD_HOSTS = env_list('STUDIO_DOWNLOAD_HOSTS',
    '.murf.ai,.amazonaws.com,storage.googleapis.com,.storage.googleapis.com')

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TASK_IGNORE_RESULT = True  # PostgreSQL est la source de vérité.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_TASK_PUBLISH_RETRY = False  # Beat reprendra les travaux en attente.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 1200
CELERY_BROKER_TRANSPORT_OPTIONS = {'visibility_timeout': 3600}
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'studio-reconcile': {'task': 'studio.tasks.dispatch_jobs', 'schedule': 30.0},
    'credits-reconcile': {'task': 'credits.tasks.reconcile_payments', 'schedule': 300.0},
    'credits-webhooks': {'task': 'credits.tasks.dispatch_webhooks', 'schedule': 30.0},
    'murf-credit-monitor': {'task': 'supervision.tasks.refresh_murf_credits', 'schedule': 300.0},
}

# Portefeuille prépayé : 1 crédit = 1 minute entamée, par langue.
CREDITS_ENABLED = env_bool('CREDITS_ENABLED', default=True) 
GENIUSPAY_API_KEY = os.getenv('GENIUSPAY_API_KEY') 
GENIUSPAY_API_SECRET = os.getenv('GENIUSPAY_API_SECRET')
GENIUSPAY_WEBHOOK_SECRET_LIVE = os.getenv('GENIUSPAY_WEBHOOK_SECRET_LIVE')

 
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'


# Envoi réel SMTP configurable, ou affichage dans le terminal en développement.
EMAIL_DELIVERY = os.getenv('EMAIL_DELIVERY', 'console').strip().lower()
if EMAIL_DELIVERY not in {'console', 'smtp'}:
    raise ImproperlyConfigured('EMAIL_DELIVERY doit valoir console ou smtp.')
smtp_username = os.getenv('EMAIL_HOST_USER', '').strip()
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', '').strip() or smtp_username or 'Dublao <noreply@localhost>'
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[Dublao] '

if EMAIL_DELIVERY == 'smtp':
    email_host = os.getenv('EMAIL_HOST', '').strip()
    email_password = os.getenv('EMAIL_HOST_PASSWORD', '')
    email_tls = env_bool('EMAIL_USE_TLS', default=True)
    email_ssl = env_bool('EMAIL_USE_SSL', default=False)
    if not email_host or not smtp_username or not email_password:
        raise ImproperlyConfigured('SMTP nécessite EMAIL_HOST, EMAIL_HOST_USER et EMAIL_HOST_PASSWORD dans .env.')
    if email_tls == email_ssl:
        raise ImproperlyConfigured('SMTP nécessite exactement une option TLS ou SSL activée.')
    MAILERS = {'default': {
        'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
        'OPTIONS': {
            'host': email_host,
            'port': int(os.getenv('EMAIL_PORT', '465' if email_ssl else '587')),
            'username': smtp_username,
            'password': email_password,
            'use_tls': email_tls,
            'use_ssl': email_ssl,
            'timeout': 20,
        },
    }}
else:
    MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.console.EmailBackend'}}
