# backend/routing.py
from django.urls import re_path
from backend.consumers import LeadConsumer

websocket_urlpatterns = [
    re_path(r'ws/leads/(?P<group_name>\w+)/$', LeadConsumer.as_asgi()),
]
