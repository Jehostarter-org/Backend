from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

import os

# Set the GDAL library path
GDAL_LIBRARY_PATH = r'C:\GDAL\bin\gdal.dll'

# Also add to system PATH so Django can find dependencies
os.environ['PATH'] = r'C:\GDAL\bin;' + os.environ.get('PATH', '')

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY    = config('SECRET_KEY')
DEBUG         = config('DEBUG', cast=bool, default=False)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv(), default='localhost,127.0.0.1')
ADMIN_REGISTRATION_SECRET = config('ADMIN_REGISTRATION_SECRET', default='').strip()

INSTALLED_APPS = [
    # ── Django Core ───────────────────────────────────────────────────────────
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # ── Third-party ───────────────────────────────────────────────────────────
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'channels',
    'strawberry_django',
    'whitenoise',
    'django_extensions',

    # ── Local Apps ────────────────────────────────────────────────────────────
    'users',
    'memberships',
    'shops',
    'services',
    'community',
    'notifications',
    'portal',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',         # must be first
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
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'jehostarter',
        'USER': 'postgres',
        'PASSWORD': 'Benjamin*247',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# ─── Redis / Channel Layer ────────────────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [config('REDIS_URL', default='redis://127.0.0.1:6379')],
        },
    },
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
STATIC_URL          = '/static/'
STATIC_ROOT         = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── CORS & CSRF ──────────────────────────────────────────────────────────────
# CORS controls which origins browsers allow to make cross-origin requests.
# CSRF_TRUSTED_ORIGINS controls which origins Django accepts POST/PUT/PATCH
# requests from (including GraphQL mutations and REST writes).
# Both must include localhost:3000 for local Next.js development.

# Always load CSRF_TRUSTED_ORIGINS from .env first, then add development defaults
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv(), default='')

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True

    # Development origins that must be trusted
    development_origins = [
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
    ]
    
    # Add development origins to CSRF trusted origins (avoid duplicates)
    for origin in development_origins:
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

    # Allow all headers and methods for development
    CORS_ALLOW_HEADERS = [
        'accept',
        'accept-encoding',
        'authorization',
        'content-type',
        'dnt',
        'origin',
        'user-agent',
        'x-csrftoken',
        'x-requested-with',
    ]
    CORS_ALLOW_METHODS = [
        'DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT',
    ]
    # Allow cookies/auth headers in cross-origin requests
    CORS_ALLOW_CREDENTIALS = True

else:
    CORS_ALLOWED_ORIGINS  = config('CORS_ALLOWED_ORIGINS', cast=Csv(), default='')
    # In production, use only what's in .env
    if not CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = []
    CORS_ALLOW_CREDENTIALS = True

# ─── HTTPS / Security Headers (production only) ───────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True
    SECURE_SSL_REDIRECT            = True
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
    SECURE_BROWSER_XSS_FILTER      = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    X_FRAME_OPTIONS                = 'DENY'

# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Email ──────────────────────────────────────────────────────────────────────
# Set EMAIL_HOST_USER + EMAIL_HOST_PASSWORD in backend/.env to send real mail (SMTP).
# Without credentials, OTP emails print to the Django runserver console only.
_email_user = config('EMAIL_HOST_USER', default='').strip()
_email_pass = config('EMAIL_HOST_PASSWORD', default='').strip()
_email_backend = config('EMAIL_BACKEND', default='').strip()

if _email_backend:
    EMAIL_BACKEND = _email_backend
elif _email_user and _email_pass:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

EMAIL_HOST          = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT          = config('EMAIL_PORT', cast=int, default=587)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS', cast=bool, default=True)
EMAIL_HOST_USER     = _email_user
EMAIL_HOST_PASSWORD = _email_pass
DEFAULT_FROM_EMAIL  = config(
    'DEFAULT_FROM_EMAIL',
    default=_email_user or 'Jehostarter <noreply@jehostarter.com>',
)
FRONTEND_URL        = config('FRONTEND_URL', default='http://localhost:3000')
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
# Strawberry handles its own auth — CSRF exemption is needed because
# GraphQL clients send JSON (not form data) and manage auth via Bearer token.
STRAWBERRY_DJANGO = {
    'CSRF_EXEMPT': True,   # exempt /graphql/ from Django's CSRF middleware
}

# ─── Platform Config ──────────────────────────────────────────────────────────
COUNTRY_CURRENCY_MAP = {
    'NG': 'NGN', 'GH': 'GHS', 'CM': 'XAF', 'KE': 'KES',
    'ZA': 'ZAR', 'ZW': 'USD', 'UG': 'UGX',
    'IN': 'INR', 'NP': 'NPR', 'CN': 'CNY',
    'GB': 'GBP', 'FR': 'EUR', 'ES': 'EUR', 'PT': 'EUR', 'CY': 'EUR',
    'US': 'USD', 'CA': 'CAD', 'AU': 'AUD',
}
SUPPORTED_COUNTRIES = list(COUNTRY_CURRENCY_MAP.keys())