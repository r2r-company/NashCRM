# asterisk/admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import SIPAccount

@admin.register(SIPAccount)
class SIPAccountAdmin(ModelAdmin):
    list_display = ("user", "sip_username", "domain", "ws_url")
    search_fields = ("user__username", "sip_username", "domain")
