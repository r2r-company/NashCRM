# 🔥 ТИМЧАСОВИЙ DEBUG ДЛЯ backend/urls.py
# Додайте це на початок файлу для діагностики

from django.urls import path, include
from django.http import JsonResponse
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


# 🔍 ДІАГНОСТИЧНИЙ VIEW
def debug_api_status(request):
    """Діагностичний endpoint для перевірки API"""
    import sys
    from django.conf import settings

    return JsonResponse({
        "status": "✅ API працює!",
        "debug_mode": settings.DEBUG,
        "python_path": sys.path,
        "installed_apps": settings.INSTALLED_APPS,
        "message": "Якщо ви бачите це повідомлення - маршрутизація працює"
    })


# 🔍 БЕЗПЕЧНІ ІМПОРТИ З ОБРОБКОЮ ПОМИЛОК
try:
    from backend.views import (
        ping, LeadViewSet, LoginView, ClientViewSet, ExternalLeadView,
        LeadsReportView, geocode_address, funnel_data, leads_report,
        all_payments, MyTokenObtainPairView, list_managers, ManagerViewSet, CreateLeadView,
        client_segments_for_marketing, create_follow_up_tasks, update_all_client_metrics,
        crm_dashboard, ClientTaskViewSet, ClientInteractionViewSet
    )

    VIEWS_IMPORTED = True
    IMPORT_ERROR = None
except ImportError as e:
    VIEWS_IMPORTED = False
    IMPORT_ERROR = str(e)


    # Заглушки для критичних view-ів
    def error_view(request):
        return JsonResponse({
            "error": "Import Error",
            "details": IMPORT_ERROR,
            "message": "Проблема з імпортом view-ів"
        }, status=500)


    ping = error_view
    ClientViewSet = None

# 🛠️ ROUTER З ПЕРЕВІРКОЮ
router = DefaultRouter()

# Реєструємо тільки якщо імпорти успішні
if VIEWS_IMPORTED and ClientViewSet:
    try:
        router.register(r'leads', LeadViewSet, basename='lead')
        router.register(r'clients', ClientViewSet, basename='client')
        router.register(r'managers', ManagerViewSet, basename='manager')
        router.register(r'client-interactions', ClientInteractionViewSet, basename='client-interaction')
        router.register(r'client-tasks', ClientTaskViewSet, basename='client-task')
        ROUTER_REGISTERED = True
    except Exception as e:
        ROUTER_REGISTERED = False
        ROUTER_ERROR = str(e)
else:
    ROUTER_REGISTERED = False
    ROUTER_ERROR = "Views not imported"

# 🔥 URL PATTERNS
urlpatterns = [
    # Діагностичні endpoints
    path('debug/', debug_api_status, name='debug_api'),
    path('status/', lambda r: JsonResponse({
        "views_imported": VIEWS_IMPORTED,
        "router_registered": ROUTER_REGISTERED,
        "import_error": IMPORT_ERROR,
        "router_error": ROUTER_ERROR if not ROUTER_REGISTERED else None
    })),
]

# Додаємо основні URL тільки якщо імпорти успішні
if VIEWS_IMPORTED:
    urlpatterns.extend([
        path('ping/', ping),
        path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
        path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
        path('login/', LoginView.as_view()),
        path('external-lead/', ExternalLeadView.as_view()),
        path('reports/leads/', LeadsReportView.as_view(), name='api_leads_report'),
        path("geocode/", geocode_address),
        path("funnel/", funnel_data),
        path("leads-report/", leads_report),
        path("payments/", all_payments),
        path("leads/create/", CreateLeadView.as_view(), name="create_lead"),

        # CRM Dashboard
        path('crm/dashboard/', crm_dashboard, name='crm_dashboard'),

        # Управління клієнтами
        path('crm/update-metrics/', update_all_client_metrics, name='update_client_metrics'),
        path('crm/create-tasks/', create_follow_up_tasks, name='create_follow_up_tasks'),
        path('crm/segments/', client_segments_for_marketing, name='client_segments'),
    ])

# Додаємо router URL тільки якщо він зареєстрований
if ROUTER_REGISTERED:
    urlpatterns += router.urls
else:
    # Заглушка для /clients/
    urlpatterns.append(
        path('clients/', lambda r: JsonResponse({
            "error": "ClientViewSet not available",
            "details": ROUTER_ERROR,
            "suggestion": "Перевірте імпорти в backend/views.py"
        }, status=500))
    )