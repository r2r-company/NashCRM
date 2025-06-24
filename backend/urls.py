from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from backend.views import (
    ping, LeadViewSet, LoginView, ClientViewSet, ExternalLeadView,
    LeadsReportView, geocode_address, funnel_data, leads_report,
    all_payments, MyTokenObtainPairView, list_managers, ManagerViewSet, CreateLeadView,
    client_segments_for_marketing, create_follow_up_tasks, update_all_client_metrics,
    crm_dashboard, ClientTaskViewSet, ClientInteractionViewSet
)

router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'clients', ClientViewSet, basename='client')  # ← ДОДАНО BASENAME
router.register(r'managers', ManagerViewSet, basename='manager')
router.register(r'client-interactions', ClientInteractionViewSet, basename='client-interaction')
router.register(r'client-tasks', ClientTaskViewSet, basename='client-task')

urlpatterns = [
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
]

urlpatterns += router.urls