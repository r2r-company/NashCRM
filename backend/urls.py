from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from backend.views import (
    ping, LoginView, MyTokenObtainPairView,
    LeadViewSet, ClientViewSet, ManagerViewSet,
    ExternalLeadView, leads_report, LeadsReportView,
    geocode_address, funnel_data, all_payments,
    list_managers, map_search_view, leads_report_page,
    ClientInteractionViewSet, ClientTaskViewSet,
    crm_dashboard, update_all_client_metrics,
    create_follow_up_tasks, client_segments_for_marketing,
    CreateLeadView, check_lead_duplicate, map_config_api, lead_statuses
)

# 🚀 Стандартний роутер Django REST Framework
router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'managers', ManagerViewSet, basename='manager')  # ✅ Основний маршрут для менеджерів
router.register(r'interactions', ClientInteractionViewSet, basename='interaction')
router.register(r'tasks', ClientTaskViewSet, basename='task')

urlpatterns = [
    # 🔐 AUTHENTICATION
    path('ping/', ping, name='ping'),
    path('auth/token/', MyTokenObtainPairView.as_view(), name='auth_token'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth_refresh'),
    path('auth/login/', LoginView.as_view(), name='auth_login'),

    # 📊 CRM DASHBOARD
    path('crm/dashboard/', crm_dashboard, name='crm_dashboard'),
    path('crm/update-metrics/', update_all_client_metrics, name='crm_update_metrics'),
    path('crm/create-tasks/', create_follow_up_tasks, name='crm_create_tasks'),
    path('crm/segments/', client_segments_for_marketing, name='crm_segments'),

    # 📈 ANALYTICS & REPORTS
    path('analytics/funnel/', funnel_data, name='analytics_funnel'),
    path('analytics/leads-report/', leads_report, name='analytics_leads_report'),
    path('analytics/detailed-report/', LeadsReportView.as_view(), name='analytics_detailed'),
    path('analytics/payments/', all_payments, name='analytics_payments'),

    # 🌍 UTILITIES
    path('utils/geocode/', geocode_address, name='utils_geocode'),
    path('utils/map-config/', map_config_api, name='utils_map_config'),

    # 📥 EXTERNAL API
    path('external/leads/', ExternalLeadView.as_view(), name='external_leads'),
    path('leads/create/', CreateLeadView.as_view(), name='leads_create'),
    path('leads/check-duplicate/', check_lead_duplicate, name='leads_check_duplicate'),

    # 🔄 CUSTOM ACTIONS для лідів
    path('leads/<int:lead_id>/update-status/',
         LeadViewSet.as_view({'put': 'update_status', 'patch': 'update_status'}),
         name='lead-update-status'),
    path('leads/<int:lead_id>/add-payment/',
         LeadViewSet.as_view({'post': 'add_payment'}),
         name='lead-add-payment'),
    path('leads/<int:lead_id>/upload-file/',
         LeadViewSet.as_view({'post': 'upload_file'}),
         name='lead-upload-file'),

    # 📋 LEGACY ENDPOINTS (для зворотної сумісності)
    path('managers/list/', list_managers, name='list_managers_legacy'),  # ✅ Перейменовано щоб не конфліктувати

    # 📊 ADMIN PAGES
    path('reports/leads/', leads_report_page, name='leads_report_page'),
    path('admin/map-search/', map_search_view, name='map_search'),

    path('statuses/', lead_statuses, name='lead_statuses'),

    # 🚀 ROUTER URLS (має бути в кінці)
    path('', include(router.urls)),
]

# 📝 URL PATTERNS SUMMARY:
#
# 🔐 Авторизація:
# - POST /api/auth/token/ - Отримання JWT токенів
# - POST /api/auth/refresh/ - Оновлення токенів
# - POST /api/auth/login/ - Стандартна авторизація
# - GET /api/ping/ - Перевірка стану системи
#
# 👥 Менеджери (REST):
# - GET /api/managers/ - Список менеджерів
# - POST /api/managers/ - Створення менеджера
# - GET /api/managers/{id}/ - Деталі менеджера
# - PUT/PATCH /api/managers/{id}/ - Оновлення менеджера
# - DELETE /api/managers/{id}/ - Видалення менеджера
#
# 🎯 Ліди (REST):
# - GET /api/leads/ - Список лідів
# - POST /api/leads/ - Створення ліда
# - GET /api/leads/{id}/ - Деталі ліда
# - PUT/PATCH /api/leads/{id}/ - Оновлення ліда
# - DELETE /api/leads/{id}/ - Видалення ліда
# - PUT /api/leads/{id}/update-status/ - Зміна статусу
# - POST /api/leads/{id}/add-payment/ - Додавання платежу
# - POST /api/leads/{id}/upload-file/ - Завантаження файлу
#
# 👤 Клієнти (REST):
# - GET /api/clients/ - Список клієнтів
# - POST /api/clients/ - Створення клієнта
# - GET /api/clients/{id}/ - Деталі клієнта
# - PUT/PATCH /api/clients/{id}/ - Оновлення клієнта
# - DELETE /api/clients/{id}/ - Видалення клієнта
# - GET /api/clients/leads/{id}/ - Ліди клієнта
# - GET /api/clients/payments/{id}/ - Платежі клієнта
# - GET /api/clients/temperature-stats/ - Статистика по температурі
# - GET /api/clients/akb-segments/ - Сегменти AKB
# - GET /api/clients/rfm-analysis/ - RFM аналіз
# - GET /api/clients/churn-risk/ - Ризик відтоку
# - GET /api/clients/hot-leads/ - Гарячі ліди
# - GET /api/clients/journey/{id}/ - Подорож клієнта
# - POST /api/clients/update-temperature/{id}/ - Оновлення температури
#
# 💬 Взаємодії (REST):
# - GET /api/interactions/ - Список взаємодій
# - POST /api/interactions/ - Створення взаємодії
# - GET /api/interactions/{id}/ - Деталі взаємодії
# - PUT/PATCH /api/interactions/{id}/ - Оновлення взаємодії
# - DELETE /api/interactions/{id}/ - Видалення взаємодії
#
# 📋 Задачі (REST):
# - GET /api/tasks/ - Список задач
# - POST /api/tasks/ - Створення задачі
# - GET /api/tasks/{id}/ - Деталі задачі
# - PUT/PATCH /api/tasks/{id}/ - Оновлення задачі
# - DELETE /api/tasks/{id}/ - Видалення задачі
# - GET /api/tasks/my-tasks/ - Мої задачі
# - GET /api/tasks/overdue-tasks/ - Прострочені задачі
#
# 📊 CRM Dashboard:
# - GET /api/crm/dashboard/ - Головний дашборд
# - POST /api/crm/update-metrics/ - Оновлення метрик
# - POST /api/crm/create-tasks/ - Створення задач
# - GET /api/crm/segments/ - Сегменти для маркетингу
#
# 📈 Аналітика:
# - GET /api/analytics/funnel/ - Воронка продажів
# - GET /api/analytics/leads-report/ - Звіт по лідах
# - GET /api/analytics/detailed-report/ - Детальний звіт
# - GET /api/analytics/payments/ - Звіт по платежах
#
# 🌍 Утиліти:
# - GET /api/utils/geocode/ - Геокодування адреси
# - GET /api/utils/map-config/ - Конфігурація карти
#
# 📥 Зовнішні API:
# - POST /api/external/leads/ - Створення ліда ззовні
# - POST /api/leads/create/ - Створення ліда
# - POST /api/leads/check-duplicate/ - Перевірка дублікатів
