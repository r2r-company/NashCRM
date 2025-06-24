"""
Django settings for NashCRM project.
ОПТИМІЗОВАНО для швидкодії БЕЗ пагінації
"""
import os
from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-q^cstj+vp83u^gqy_864z5um7sviic5=bfnl%esn6p4-jzk^3='

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'nashcrm.onrender.com',
    'localhost',
    '127.0.0.1',
]

# 🚀 НАЛАШТУВАННЯ REST API (БЕЗ ПАГІНАЦІЇ!)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # 🚨 ВІДКЛЮЧЕНА ПАГІНАЦІЯ (щоб API повертав прямий масив)
    'DEFAULT_PAGINATION_CLASS': None,

    # 🚀 ОПТИМІЗАЦІЯ для швидкодії
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

# 🚀 КЕШУВАННЯ для швидкодії
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'nashcrm-cache',
        'TIMEOUT': 300,  # 5 хвилин
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
            'CULL_FREQUENCY': 3,
        }
    }
}

# Application definition
GOOGLE_MAPS_API_KEY = "AIzaSyCbJKRdLawZO1Y61MORHULsFbxGbQLlrsk"

ASGI_APPLICATION = "NashCRM.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=60),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

INSTALLED_APPS = [
    'corsheaders',
    'channels',
    'unfold',
    'whatsapp',
    'rest_framework',
    'backend',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

# 🚀 ОПТИМІЗОВАНИЙ MIDDLEWARE
MIDDLEWARE = [
    # 🚀 КЕШ (швидкість)
    'django.middleware.cache.UpdateCacheMiddleware',

    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # 🚀 КЕШ (кінець pipeline)
    'django.middleware.cache.FetchFromCacheMiddleware',
]

ROOT_URLCONF = 'NashCRM.urls'

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

WSGI_APPLICATION = 'NashCRM.wsgi.application'

# 🚀 ОПТИМІЗОВАНА БАЗА ДАНИХ
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # 🚀 SQLite оптимізація
        'OPTIONS': {
            'timeout': 30,
            'init_command': '''
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA cache_size=1000;
                PRAGMA temp_store=MEMORY;
                PRAGMA mmap_size=134217728;
            ''',
        },
        'TEST': {
            'NAME': ':memory:',
        },
    }
}

# 🚀 НАЛАШТУВАННЯ КЕШУ для сесій і DB
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'

# Password validation
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
LANGUAGE_CODE = 'uk'
TIME_ZONE = 'Europe/Kyiv'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 🚀 ЛОГУВАННЯ для відстеження швидкодії
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'INFO' if DEBUG else 'WARNING',
        },
    },
}

def dashboard_callback(request, context):
    context.update({"sample": "example"})
    return context

def environment_callback(request):
    return

def badge_callback(request):
    return 3

def permission_callback(request):
    return request.user.has_perm("sample_app.change_model")

UNFOLD = {
    "SITE_TITLE": "Custom suffix in <title> tag",
    "SITE_HEADER": "Appears in sidebar at the top",
    "SITE_SUBHEADER": "Appears under SITE_HEADER",

    "SITE_URL": "/",
    "SITE_ICON": {
        "light": lambda request: static("backend/img/crm.png"),
        "dark": lambda request: static("backend/img/crm.png"),
    },
    "SITE_LOGO": {
        "light": lambda request: static("backend/img/crm.png"),
        "dark": lambda request: static("backend/img/crm.png"),
    },
    "SITE_SYMBOL": "speed",
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "sizes": "32x32",
            "type": "image/svg+xml",
            "href": lambda request: static("favicon.svg"),
        },
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SHOW_BACK_BUTTON": False,
    "ENVIRONMENT": environment_callback,
    "ENVIRONMENT_TITLE_PREFIX": environment_callback,
    "DASHBOARD_CALLBACK": dashboard_callback,
    "THEME": "dark",
    "LOGIN": {
        "image": lambda request: static("sample/login-bg.jpg"),
        "redirect_after": lambda request: reverse_lazy("admin:APP_MODEL_changelist"),
    },
    "STYLES": [
        lambda request: static("backend/css/style.css"),
    ],
    "SCRIPTS": [
        lambda request: static("js/script.js"),
    ],
    "BORDER_RADIUS": "6px",
    "COLORS": {
        "base": {
            "50": "249, 250, 251",
            "100": "243, 244, 246",
            "200": "229, 231, 235",
            "300": "209, 213, 219",
            "400": "156, 163, 175",
            "500": "107, 114, 128",
            "600": "75, 85, 99",
            "700": "55, 65, 81",
            "800": "31, 41, 55",
            "900": "17, 24, 39",
            "950": "3, 7, 18",
        },
        "primary": {
            "50": "250, 245, 255",
            "100": "243, 232, 255",
            "200": "233, 213, 255",
            "300": "216, 180, 254",
            "400": "192, 132, 252",
            "500": "168, 85, 247",
            "600": "147, 51, 234",
            "700": "126, 34, 206",
            "800": "107, 33, 168",
            "900": "88, 28, 135",
            "950": "59, 7, 100",
        },
        "font": {
            "subtle-light": "var(--color-base-500)",
            "subtle-dark": "var(--color-base-400)",
            "default-light": "var(--color-base-600)",
            "default-dark": "var(--color-base-300)",
            "important-light": "var(--color-base-900)",
            "important-dark": "var(--color-base-100)",
        },
    },
    "EXTENSIONS": {
        "modeltranslation": {
            "flags": {
                "en": "🇬🇧",
                "fr": "🇫🇷",
                "nl": "🇧🇪",
            },
        },
    },
    "SIDEBAR": {
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Продажі"),
                "separator": True,
                "items": [
                    {
                        "title": "Ліди",
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:backend_lead_changelist"),
                    },
                    {
                        "title": "Фінансові операції",
                        "icon": "payments",
                        "link": reverse_lazy("admin:backend_leadpaymentoperation_changelist"),
                    },
                    {
                        "title": "Клієнти",
                        "icon": "person",
                        "link": reverse_lazy("admin:backend_client_changelist"),
                    },
                    {
                        "title": "Email налаштування",
                        "icon": "email",
                        "link": reverse_lazy("admin:backend_emailintegrationsettings_changelist"),
                    },
                    {
                        "title": "Звіт по лідах",
                        "icon": "bar_chart",
                        "link": reverse_lazy("admin_leads_report"),
                    },
                ],
            },
        ],
    },
    "TABS": [
        {
            "models": [
                "app_label.model_name_in_lowercase",
            ],
            "items": [
                {
                    "title": _("Your custom title"),
                    "link": reverse_lazy("admin:backend_lead_changelist"),
                },
            ],
        },
    ],
}

CORS_ALLOWED_ORIGINS = [
    "https://nash-web-crm.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_HEADERS = [
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

CORS_ALLOWED_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CSRF_TRUSTED_ORIGINS = [
    "https://nash-web-crm.vercel.app",
    "https://nashcrm.onrender.com",
]