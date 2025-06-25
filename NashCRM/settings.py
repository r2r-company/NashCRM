"""
Django settings for NashCRM project.
ОПТИМІЗОВАНО для роботи бухгалтера - актуальні дані в реальному часі
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

# 🚀 РОЗУМНЕ КЕШУВАННЯ для бухгалтерської роботи
# Як професійний бухгалтер потребує актуальних даних
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'nashcrm-realtime-cache',
        'TIMEOUT': 30,  # 🚀 СКОРОЧУЄМО до 30 секунд замість 5 хвилин
        'OPTIONS': {
            'MAX_ENTRIES': 2000,  # Збільшуємо кількість записів
            'CULL_FREQUENCY': 4,  # Частіше очищуємо старі записи
        }
    },
    # 🚀 ДОДАТКОВИЙ КЕШ для статичних даних (адреси, менеджери)
    'static_data': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'nashcrm-static-cache',
        'TIMEOUT': 600,  # 10 хвилин для статичних даних
        'OPTIONS': {
            'MAX_ENTRIES': 500,
            'CULL_FREQUENCY': 3,
        }
    }
}

# 🚀 КОНФІГУРАЦІЯ КЕШУ ДЛЯ РІЗНИХ ТИПІВ ДАНИХ
CACHE_TIMEOUTS = {
    # Фінансові дані - мінімальний кеш
    'funnel': 30,           # 30 секунд
    'payments': 60,         # 1 хвилина
    'reports': 60,          # 1 хвилина
    'lead_status': 0,       # БЕЗ КЕШУ! (найважливіше)

    # Довідкові дані - помірний кеш
    'managers': 120,        # 2 хвилини
    'clients': 30,          # 30 секунд

    # Статичні дані - довгий кеш
    'geocoding': 86400,     # 1 день
    'settings': 3600,       # 1 година
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

# 🚀 ОПТИМІЗОВАНИЙ MIDDLEWARE для бухгалтерської роботи
MIDDLEWARE = [
    # 🚀 СЕЛЕКТИВНИЙ КЕШ тільки для статичних сторінок
    # 'django.middleware.cache.UpdateCacheMiddleware',  # ВИМКНЕНО для актуальних даних

    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # 🚀 СЕЛЕКТИВНИЙ КЕШ
    # 'django.middleware.cache.FetchFromCacheMiddleware',  # ВИМКНЕНО
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

# 🚀 ОПТИМІЗОВАНА БАЗА ДАНИХ для бухгалтерської роботи
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # 🚀 SQLite оптимізація для частих читань/записів
        'OPTIONS': {
            'timeout': 30,
            'init_command': '''
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA cache_size=2000;
                PRAGMA temp_store=MEMORY;
                PRAGMA mmap_size=268435456;
                PRAGMA optimize;
            ''',
        },
        'TEST': {
            'NAME': ':memory:',
        },
    }
}

# 🚀 НАЛАШТУВАННЯ СЕСІЙ без агресивного кешування
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Тільки БД
SESSION_COOKIE_AGE = 86400  # 1 день
SESSION_SAVE_EVERY_REQUEST = False  # Економимо записи в БД

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

# 🚀 ДЕТАЛЬНЕ ЛОГУВАННЯ для контролю швидкодії
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING' if not DEBUG else 'INFO',
            'propagate': False,
        },
        'backend.views': {
            'handlers': ['console', 'file'] if DEBUG else ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# 🚀 СТВОРЮЄМО ПАПКУ ДЛЯ ЛОГІВ
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

def dashboard_callback(request, context):
    """Додаткова інформація для дашборду"""
    context.update({
        "cache_status": "Оптимізовано для бухгалтерії",
        "realtime_data": True
    })
    return context

def environment_callback(request):
    return "PRODUCTION" if not DEBUG else "DEVELOPMENT"

def badge_callback(request):
    # Показуємо кількість активних лідів
    from backend.models import Lead
    return Lead.objects.filter(status__in=['queued', 'in_work']).count()

def permission_callback(request):
    return request.user.has_perm("backend.change_lead")

UNFOLD = {
    "SITE_TITLE": "NashCRM - Система обліку",
    "SITE_HEADER": "CRM для професійного обліку",
    "SITE_SUBHEADER": "Актуальні дані в реальному часі",

    "SITE_URL": "/",
    "SITE_ICON": {
        "light": lambda request: static("backend/img/crm.png"),
        "dark": lambda request: static("backend/img/crm.png"),
    },
    "SITE_LOGO": {
        "light": lambda request: static("backend/img/crm.png"),
        "dark": lambda request: static("backend/img/crm.png"),
    },
    "SITE_SYMBOL": "account_balance",  # Іконка бухгалтерії
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
    "ENVIRONMENT_TITLE_PREFIX": lambda request: "📊 " if not DEBUG else "🔧 ",
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
            "500": "34, 197, 94",   # Зелений для бухгалтерії
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
                "title": _("💰 Фінансовий облік"),
                "separator": True,
                "items": [
                    {
                        "title": "📋 Ліди",
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:backend_lead_changelist"),
                        "badge": badge_callback,
                    },
                    {
                        "title": "💳 Фінансові операції",
                        "icon": "payments",
                        "link": reverse_lazy("admin:backend_leadpaymentoperation_changelist"),
                    },
                    {
                        "title": "👥 Клієнти",
                        "icon": "person",
                        "link": reverse_lazy("admin:backend_client_changelist"),
                    },
                    {
                        "title": "📊 Звіт по лідах",
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
                        "title": "📧 Email налаштування",
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
                    "title": _("📊 Фінансовий аналіз"),
                    "link": reverse_lazy("admin_leads_report"),
                },
                {
                    "title": _("📋 Всі ліди"),
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

# 🚀 ДОДАТКОВІ НАЛАШТУВАННЯ ДЛЯ БУХГАЛТЕРСЬКОЇ РОБОТИ
# Автоматичне збереження змін кожні 30 секунд
AUTOSAVE_INTERVAL = 30

# Перевірка актуальності даних
DATA_FRESHNESS_CHECK = True

# Сповіщення про зміни в фінансах
FINANCIAL_ALERTS = True