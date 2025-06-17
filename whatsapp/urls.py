# whatsapp/urls.py

from django.urls import path
from .views import WhatsAppReceiveMessage, WhatsAppSendMessage, WhatsAppCloudSendView

urlpatterns = [
    path('receive/', WhatsAppReceiveMessage.as_view()),
    path('send/', WhatsAppSendMessage.as_view()),
    path("cloud-send/", WhatsAppCloudSendView.as_view()),

]
