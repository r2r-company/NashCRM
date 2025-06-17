from django.contrib import admin
from .models import WhatsAppMessage

@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "message", "direction", "timestamp", "status")
    list_filter = ("direction", "status")
    search_fields = ("phone_number", "message", "external_id")



