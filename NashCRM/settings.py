"""
Django settings for NashCRM project.
ОПТИМІЗОВАНО для швидкої роботи бухгалтера - БЕЗ ГАЛЬМУВАННЯ!
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

DOMAIN = "https://nashcrm.onrender.com"

# 🚀 ШВИДКІ НАЛАШТУВАННЯ REST API з пагінацією
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # 🚀 ОБОВ'ЯЗКОВА ПАГІНАЦІЯ для швидкодії!
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,  # По 20 записів - швидко завантажується

    # 🚀 ШВИДКІ РЕНДЕРИ
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

# 🚀 ВІДКЛЮЧАЄМО КЕШ для максимальної швидкодії
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',  # БЕЗ КЕШУ!
    }
}

# 🚀 ВСІ TIMEOUT НА 0 - БЕЗ ЗАТРИМОК
CACHE_TIMEOUTS = {
    'funnel': 0,
    'payments': 0,
    'reports': 0,
    'lead_status': 0,
    'managers': 0,
    'clients': 0,
    'geocoding': 0,
    'settings': 0,
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
    'asterisk',
]

# 🚀 ШВИДКИЙ MIDDLEWARE без кешування
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

# 🚀 МАКСИМАЛЬНО ШВИДКА БАЗА ДАНИХ
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 2,  # 🚀 ШВИДКИЙ TIMEOUT - 2 секунди!
            'init_command': '''
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA cache_size=10000;
                PRAGMA temp_store=MEMORY;
                PRAGMA mmap_size=268435456;
            ''',
        },
        'TEST': {
            'NAME': ':memory:',
        },
    }
}

# 🚀 ШВИДКІ СЕСІЇ
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 1 день
SESSION_SAVE_EVERY_REQUEST = False

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

# 🚀 МІНІМАЛЬНЕ ЛОГУВАННЯ для швидкодії
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'ERROR',  # Тільки помилки!
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'ERROR',
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# 🚀 СТВОРЮЄМО ПАПКУ ДЛЯ ЛОГІВ (якщо потрібно)
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

def dashboard_callback(request, context):
    """Додаткова інформація для дашборду"""
    context.update({
        "cache_status": "Швидкий режим",
        "realtime_data": True
    })
    return context

def environment_callback(request):
    return "PRODUCTION" if not DEBUG else "DEVELOPMENT"

def badge_callback(request):
    # 🚀 ШВИДКИЙ підрахунок лідів
    try:
        from backend.models import Lead
        return Lead.objects.filter(status__in=['queued', 'in_work']).count()
    except:
        return 0

def permission_callback(request):
    return request.user.has_perm("backend.change_lead")

UNFOLD = {
    "SITE_TITLE": "NashCRM - Швидка система",
    "SITE_HEADER": "CRM для швидкого обліку",
    "SITE_SUBHEADER": "Максимальна швидкодія",

    "SITE_URL": "/",
    "SITE_ICON": {
        "light": lambda request: static("backend/img/crm.png"),
        "dark": lambda request: static("backend/img/crm.png"),
    },
    "SITE_LOGO": {
        "light": lambda request: static("backend/img/crm.png"),
        "dark": lambda request: static("backend/img/crm.png"),
    },
    "SITE_SYMBOL": "speed",  # Іконка швидкості
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "sizes": "32x32",
            "type": "image/svg+xml",
            "href": lambda request: static("favicon.svg"),
        },
    ],
    "SHOW_HISTORY": False,  # Відключаємо для швидкодії
    "SHOW_VIEW_ON_SITE": False,  # Відключаємо для швидкодії
    "SHOW_BACK_BUTTON": False,
    "ENVIRONMENT": environment_callback,
    "ENVIRONMENT_TITLE_PREFIX": lambda request: "⚡ " if not DEBUG else "🔧 ",
    "DASHBOARD_CALLBACK": dashboard_callback,
    "THEME": "dark",
    "LOGIN": {
        "image": lambda request: static("sample/login-bg.jpg"),
        "redirect_after": lambda request: reverse_lazy("admin:backend_lead_changelist"),
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
            "50": "240, 253, 244",
            "100": "220, 252, 231",
            "200": "187, 247, 208",
            "300": "134, 239, 172",
            "400": "74, 222, 128",
            "500": "34, 197, 94",   # Зелений для швидкодії
            "600": "22, 163, 74",
            "700": "21, 128, 61",
            "800": "22, 101, 52",
            "900": "20, 83, 45",
            "950": "5, 46, 22",
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
                "title": _("⚡ Швидкий облік"),
                "separator": True,
                "items": [
                    {
                        "title": "📋 Ліди",
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:backend_lead_changelist"),
                        "badge": badge_callback,
                    },
                    {
                        "title": "💳 Платежі",
                        "icon": "payments",
                        "link": reverse_lazy("admin:backend_leadpaymentoperation_changelist"),
                    },
                    {
                        "title": "👥 Клієнти",
                        "icon": "person",
                        "link": reverse_lazy("admin:backend_client_changelist"),
                    },
                    {
                        "title": "📊 Звіти",
                        "icon": "bar_chart",
                        "link": reverse_lazy("admin_leads_report"),
                    },
                ],
            },
            {
                "title": _("⚙️ Налаштування"),
                "separator": True,
                "items": [
                    {
                        "title": "📧 Email",
                        "icon": "email",
                        "link": reverse_lazy("admin:backend_emailintegrationsettings_changelist"),
                    },
                ],
            },
        ],
    },
    "TABS": [
        {
            "models": [
                "backend.lead",
                "backend.leadpaymentoperation",
                "backend.client",
            ],
            "items": [
                {
                    "title": _("📊 Аналіз"),
                    "link": reverse_lazy("admin_leads_report"),
                },
                {
                    "title": _("📋 Ліди"),
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
    "http://localhost:63342",
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

# 🚀 ШВИДКІ НАЛАШТУВАННЯ
AUTOSAVE_INTERVAL = 30
DATA_FRESHNESS_CHECK = False  # Відключаємо для швидкодії
FINANCIAL_ALERTS = True