from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from backend.views import (
    ping, LeadViewSet, LoginView, ClientViewSet, ExternalLeadView,
    LeadsReportView, geocode_address, funnel_data, leads_report,
    all_payments, MyTokenObtainPairView, list_managers, ManagerViewSet, CreateLeadView
)

router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'clients', ClientViewSet)
router.register(r'managers', ManagerViewSet, basename='manager')

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
]

urlpatterns += router.urls
