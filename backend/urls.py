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
    CreateLeadView, check_lead_duplicate
)

# Стандартний роутер Django REST Framework
router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'managers', ManagerViewSet, basename='manager')
router.register(r'interactions', ClientInteractionViewSet, basename='interaction')
router.register(r'tasks', ClientTaskViewSet, basename='task')


urlpatterns = [
    # 🔐 AUTH
    path('ping/', ping, name='ping'),
    path('auth/token/', MyTokenObtainPairView.as_view(), name='auth_token'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth_refresh'),
    path('auth/login/', LoginView.as_view(), name='auth_login'),

    # 📊 CRM Dashboard
    path('crm/dashboard/', crm_dashboard, name='crm_dashboard'),
    path('crm/update-metrics/', update_all_client_metrics, name='crm_update_metrics'),
    path('crm/create-tasks/', create_follow_up_tasks, name='crm_create_tasks'),
    path('crm/segments/', client_segments_for_marketing, name='crm_segments'),

    # 📈 Analytics & Reports
    path('analytics/funnel/', funnel_data, name='analytics_funnel'),
    path('analytics/leads-report/', leads_report, name='analytics_leads_report'),
    path('analytics/detailed-report/', LeadsReportView.as_view(), name='analytics_detailed'),
    path('analytics/payments/', all_payments, name='analytics_payments'),

    # 🌍 Utils
    path('utils/geocode/', geocode_address, name='utils_geocode'),

    # 📥 External API
    path('external/leads/', ExternalLeadView.as_view(), name='external_leads'),
    path('leads/create/', CreateLeadView.as_view(), name='leads_create'),
    path('leads/check-duplicate/', check_lead_duplicate, name='leads_check_duplicate'),

    # 📋 Admin pages
    path('managers/', list_managers, name='list_managers'),
    path('admin/reports/leads/', leads_report_page, name='leads_report_page'),
    path('admin/map-search/', map_search_view, name='map_search'),



    path('', include(router.urls)),
]