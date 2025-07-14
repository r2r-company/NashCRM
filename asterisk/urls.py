# asterisk/urls.py
from django.urls import path
from .views import SIPConfigView

urlpatterns = [
    path('sip-config/', SIPConfigView.as_view()),
]
