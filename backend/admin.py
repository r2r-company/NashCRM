from django.contrib import admin, messages
from django.contrib.sites import requests
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms

from unfold.admin import ModelAdmin

from NashCRM import settings

from .models import CustomUser, Lead, Client,  LeadPaymentOperation, EmailIntegrationSettings


@admin.register(CustomUser)
class CustomUserAdmin(ModelAdmin):
    list_display = ('user', 'interface_type')
    list_filter = ('interface_type',)
    search_fields = ('user__username',)

class GoogleAddressWidget(forms.TextInput):
    class Media:
        js = (
            f'https://maps.googleapis.com/maps/api/js?key={settings.GOOGLE_MAPS_API_KEY}&libraries=places',
            'js/address_autocomplete.js',
        )

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        api_key = settings.GOOGLE_MAPS_API_KEY
        script = f'''
        <script async defer src="https://maps.googleapis.com/maps/api/js?key={api_key}&libraries=places"></script>
        '''
        return mark_safe(script + html)



class LeadAdminForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = '__all__'
        widgets = {
            'full_address': GoogleAddressWidget(),
        }


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    form = LeadAdminForm

    list_display = (
        'full_name', 'phone', 'email', 'status', 'source', 'assigned_to',
        'created_at', 'price', "id",
        'get_expected_sum', 'get_received_sum', 'get_balance_delta',
        'status_updated_at',
    )
    list_filter = ('status', 'source')
    search_fields = ('full_name', 'phone', 'email')
    actions = ['fetch_google_address']

    # ========== 🧮 Фінансові суми ==========
    def get_expected_sum(self, obj):
        return sum(p.amount for p in obj.payment_operations.filter(operation_type='expected'))
    get_expected_sum.short_description = "Очікується"

    def get_received_sum(self, obj):
        return sum(p.amount for p in obj.payment_operations.filter(operation_type='received'))
    get_received_sum.short_description = "Отримано"

    def get_balance_delta(self, obj):
        return self.get_expected_sum(obj) - self.get_received_sum(obj)
    get_balance_delta.short_description = "Різниця"

    # ========== 📍 Google Maps екшен ==========
    def fetch_google_address(self, request, queryset):
        for lead in queryset:
            if not lead.full_address:
                continue

            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                "address": lead.full_address,
                "key": settings.GOOGLE_MAPS_API_KEY
            }

            try:
                response = requests.get(url, params=params).json()
                if response["status"] == "OK":
                    result = response["results"][0]
                    lead.lat = result["geometry"]["location"]["lat"]
                    lead.lng = result["geometry"]["location"]["lng"]

                    components = {c['types'][0]: c['long_name'] for c in result['address_components']}
                    lead.country = components.get('country')
                    lead.city = components.get('locality') or components.get('administrative_area_level_1')
                    lead.postal_code = components.get('postal_code')
                    lead.street = components.get('route')
                    lead.save()
            except Exception as e:
                messages.warning(request, f"❌ Помилка для {lead.full_name}: {e}")

        self.message_user(request, "✅ Адреси підтягнуто з Google Maps")
    fetch_google_address.short_description = "🌍 Підтягнути адресу з Google Maps"

    # ========== 🧭 Кастомна сторінка мапи ==========
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["custom_links"] = [
            {
                "label": "📌 Карта пошуку адреси",
                "url": reverse("map_search"),
            },
        ]
        return super().changelist_view(request, extra_context=extra_context)



@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = (
        'full_name',
        'phone',
        'email',
        'type',
        'status',
        'company_name',
        'assigned_to',
        'created_at'
    )
    list_filter = ('status', 'type')
    search_fields = ('full_name', 'phone', 'email', 'company_name')



@admin.register(LeadPaymentOperation)
class LeadPaymentOperationAdmin(ModelAdmin):
    list_display = ('lead', 'operation_type', 'amount', 'created_at', 'comment')
    list_filter = ('operation_type', 'created_at')
    search_fields = ('lead__full_name', 'comment')



@admin.register(EmailIntegrationSettings)
class EmailIntegrationSettingsAdmin(ModelAdmin):
    list_display = ("name", "email", "imap_host", "allowed_sender", "allowed_subject_keyword")


