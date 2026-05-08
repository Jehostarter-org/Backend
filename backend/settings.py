from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure--)dhs8x%enc01ma-(1y2a+-vc41g*^ir*bepq@t(mb)i@a!m$u'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    # ── Django Core ──────────────────────────────────────────────────────────
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # ── Third-party ──────────────────────────────────────────────────────────
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'channels',            # ← WebSocket support
    'strawberry_django',   # ← GraphQL support

    # ── Local Apps ───────────────────────────────────────────────────────────
    'users',
    'memberships',
    'shops',
    'services',
    'community',
    'notifications',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

# ─── ASGI (replaces WSGI for WebSocket support) ───────────────────────────────
ASGI_APPLICATION = 'backend.asgi.application'  # ← Changed from WSGI

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

# ─── PostgreSQL Database ──────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     'jehostarter',
        'USER':     'postgres',
        'PASSWORD': 'Benjamin*247',
        'HOST':     'localhost',
        'PORT':     '5432',
    }
}

# ─── Redis Channel Layer (required for WebSocket broadcast) ───────────────────
# Redis allows multiple server processes to share WebSocket state.
# Make sure Redis is running: `redis-server` or install via https://redis.io/
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}

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

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True

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

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Jehostarter API',
    'DESCRIPTION': 'Migrant support platform API',
    'VERSION': '1.0.0',
}

COUNTRY_CURRENCY_MAP = {
    'NG': 'NGN', 'GH': 'GHS', 'CM': 'XAF', 'KE': 'KES',
    'ZA': 'ZAR', 'ZW': 'USD', 'UG': 'UGX',
    'IN': 'INR', 'NP': 'NPR', 'CN': 'CNY',
    'GB': 'GBP', 'FR': 'EUR', 'ES': 'EUR', 'PT': 'EUR', 'CY': 'EUR',
    'US': 'USD', 'CA': 'CAD', 'AU': 'AUD',
}
SUPPORTED_COUNTRIES = list(COUNTRY_CURRENCY_MAP.keys())