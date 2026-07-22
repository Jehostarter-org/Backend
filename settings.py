from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Environment Detection ────────────────────────────────────────────────────
DEBUG = config('DEBUG', cast=bool, default=False)
IS_RENDER = os.environ.get('RENDER', False)  # Render sets this automatically

# ─── GDAL / GeoDjango ─────────────────────────────────────────────────────────
# On Windows (local dev), point to your local GDAL install.
# On Render (Linux), GDAL is available system-wide — no path needed.
if os.name == 'nt':  # Windows local dev only
    GDAL_LIBRARY_PATH = r'C:\GDAL\bin\gdal.dll'
    os.environ['PATH'] = r'C:\GDAL\bin;' + os.environ.get('PATH', '')

# ─── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY    = config('SECRET_KEY')
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    cast=Csv(),
    default='localhost,127.0.0.1'
)
ADMIN_REGISTRATION_SECRET = config('ADMIN_REGISTRATION_SECRET', default='').strip()

# ─── Apps ─────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'daphne',  # MUST be first — enables ASGI for runserver

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',  # Required for PostGIS / GeoDjango

    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'channels',
    'strawberry_django',
    'whitenoise',
    'django_extensions',

    'users',
    'memberships',
    'shops',
    'services',
    'community',
    'notifications',
    'portal',
    'messaging',
]

# ─── Middleware ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',          # must be first
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF     = 'backend.urls'
ASGI_APPLICATION = 'backend.asgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

# ─── Database ─────────────────────────────────────────────────────────────────
import dj_database_url

DATABASE_URL = config('DATABASE_URL', default='')

if DATABASE_URL:
    # Production: parse the full connection URL and force PostGIS engine.
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
    DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'
else:
    # Local development: use individual credentials from .env
    DATABASES = {
        'default': {
            'ENGINE':   'django.contrib.gis.db.backends.postgis',
            'NAME':     config('DB_NAME',     default='jehostarter'),
            'USER':     config('DB_USER',     default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST':     config('DB_HOST',     default='127.0.0.1'),
            'PORT':     config('DB_PORT',     default='5432'),
        }
    }

# Persist database connections across requests (reduces connection overhead)
CONN_MAX_AGE = 600

# ─── Redis / Channel Layer ────────────────────────────────────────────────────
# Render Redis service sets REDIS_URL automatically.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [config('REDIS_URL', default='redis://127.0.0.1:6379')],
        },
    },
}

# ─── Cache (optional but recommended on Render) ───────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379'),
    }
}

# ─── Auth ─────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.ScryptPasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Static & Media ───────────────────────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── CORS & CSRF ──────────────────────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv(), default='https://jehostarter.com')

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True

    _dev_origins = [
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
    ]
    for origin in _dev_origins:
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

    CORS_ALLOW_HEADERS = [
        'accept', 'accept-encoding', 'authorization', 'content-type',
        'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
    ]
    CORS_ALLOW_METHODS  = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
    CORS_ALLOW_CREDENTIALS = True

else:
    CORS_ALLOWED_ORIGINS   = config('CORS_ALLOWED_ORIGINS', cast=Csv(), default='https://jehostarter.com')
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_HEADERS = [
        'accept', 'accept-encoding', 'authorization', 'content-type',
        'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
    ]
    CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']

# ─── HTTPS / Security Headers (production only) ───────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True
    # Dokploy/Traefik terminates SSL at the edge — Django sits behind a proxy.
    # Don't redirect to HTTPS internally; Traefik handles it.
    SECURE_SSL_REDIRECT            = False
    SECURE_PROXY_SSL_HEADER        = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    X_FRAME_OPTIONS                = 'DENY'

# ─── File Upload Limits ──────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB

# ─── Backend URL (for serializer image URLs) ─────────────────────────────────
BACKEND_URL = config('BACKEND_URL', default='https://api.jehostarter.com')

# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE      = 'en-us'
TIME_ZONE          = 'UTC'
USE_I18N           = True
USE_TZ             = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Email ────────────────────────────────────────────────────────────────────
_email_user    = config('EMAIL_HOST_USER',     default='').strip()
_email_pass    = config('EMAIL_HOST_PASSWORD', default='').strip()
_email_backend = config('EMAIL_BACKEND',       default='').strip()

if _email_backend:
    EMAIL_BACKEND = _email_backend
elif _email_user and _email_pass:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

EMAIL_HOST               = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT               = config('EMAIL_PORT', cast=int, default=587)
EMAIL_USE_TLS            = config('EMAIL_USE_TLS', cast=bool, default=True)
EMAIL_HOST_USER          = _email_user
EMAIL_HOST_PASSWORD      = _email_pass
DEFAULT_FROM_EMAIL       = config(
    'DEFAULT_FROM_EMAIL',
    default=_email_user or 'Jehostarter <noreply@jehostarter.com>',
)
FRONTEND_URL             = config('FRONTEND_URL', default='https://jehostarter.com')
EMAIL_OTP_EXPIRY_MINUTES = config('EMAIL_OTP_EXPIRY_MINUTES', cast=int, default=15)

# ─── REST Framework ───────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_RATES': {
        'signup': '3/hour',
        'login': '10/min',
        'forgot_password': '3/hour',
        'resend_verification': '3/hour',
    },
    # Use Redis for throttle cache (shared across workers)
    'DEFAULT_THROTTLE_CACHE': 'default',
    # Disable BrowsableAPI in production (API consumers only)
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ] if not DEBUG else [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# ─── JWT ──────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
}

# ─── API Docs ─────────────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE':       'Jehostarter API',
    'DESCRIPTION': 'Migrant support platform API',
    'VERSION':     '1.0.0',
}

# ─── Strawberry GraphQL ───────────────────────────────────────────────────────
STRAWBERRY_DJANGO = {
    'CSRF_EXEMPT': True,
}

# ─── Platform Config ──────────────────────────────────────────────────────────
COUNTRY_CURRENCY_MAP = {
    'NG': 'NGN', 'GH': 'GHS', 'CM': 'XAF', 'KE': 'KES',
    'ZA': 'ZAR', 'ZW': 'USD', 'UG': 'UGX',
    'IN': 'INR', 'NP': 'NPR', 'CN': 'CNY',
    'GB': 'GBP', 'FR': 'EUR', 'ES': 'EUR', 'PT': 'EUR', 'CY': 'EUR',
    'US': 'USD', 'CA': 'CAD', 'AU': 'AUD',
}
SUPPORTED_COUNTRIES      = list(COUNTRY_CURRENCY_MAP.keys())
ORS_API_KEY              = config('ORS_API_KEY', default='')
GRAPH_HOPPER_API_KEY     = config('GRAPH_HOPPER_API_KEY', default='')

# ─── Logging ──────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}