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
router.register(r'managers', ManagerViewSet, basename='manager')
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

    # 🔄 LEAD STATUS UPDATES - ЧИСТИЙ REST API
    path('leads/<int:lead_id>/status/',
         LeadViewSet.as_view({'put': 'update_status', 'patch': 'update_status', 'get': 'get_status'}),
         name='lead-status'),

    # 🔄 LEGACY URL (для зворотної сумісності)
    path('leads/<int:lead_id>/update-status/',
         LeadViewSet.as_view({'put': 'update_status', 'patch': 'update_status'}),
         name='lead-update-status-legacy'),

    # 🔄 ІНШІ CUSTOM ACTIONS для лідів
    path('leads/<int:lead_id>/add-payment/',
         LeadViewSet.as_view({'post': 'add_payment'}),
         name='lead-add-payment'),
    path('leads/<int:lead_id>/upload-file/',
         LeadViewSet.as_view({'post': 'upload_file'}),
         name='lead-upload-file'),

    # 📋 LEGACY ENDPOINTS (для зворотної сумісності)
    path('managers/list/', list_managers, name='list_managers_legacy'),

    # 📊 ADMIN PAGES
    path('reports/leads/', leads_report_page, name='leads_report_page'),
    path('admin/map-search/', map_search_view, name='map_search'),

    # 📊 GENERAL INFO
    path('statuses/', lead_statuses, name='lead_statuses'),

    # 🚀 ROUTER URLS (має бути в кінці)
    path('', include(router.urls)),
]