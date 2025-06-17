# NashCRM/asgi.py
import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
import backend.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'NashCRM.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(backend.routing.websocket_urlpatterns)
    ),
})
