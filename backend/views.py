from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.db.models import Count, Sum, DurationField, ExpressionWrapper, F, Q, Avg, Case, When, DecimalField, Prefetch
from django.shortcuts import render
from django.utils import timezone  # ← ЦЕЙ РЯДОК ВІРОГІДНО Є
from django.utils.dateparse import parse_date
from django.utils.timezone import now
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
import requests
from django.contrib.auth.models import Permission

# 🚀 ДОДАЙТЕ ЦІ ІМПОРТИ:
from datetime import datetime, timedelta

from NashCRM import settings
from backend.forms import LeadsReportForm
from backend.models import CustomUser, Lead, Client, LeadPaymentOperation, LeadFile, ClientInteraction, ClientTask
from backend.serializers import LeadSerializer, ClientSerializer, ExternalLeadSerializer, MyTokenObtainPairSerializer, \
    ManagerSerializer, ClientTaskSerializer, ClientInteractionSerializer
from backend.services.lead_creation_service import create_lead_with_logic
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

# 🚀 УТИЛІТА ДЛЯ РОЗУМНОГО ОЧИЩЕННЯ КЕШУ
from backend.validators.lead_status_validator import LeadStatusValidator, validate_lead_status_change


def smart_cache_invalidation(lead_id=None, client_phone=None, manager_id=None):
    """
    Розумне очищення кешу - тільки пов'язані дані
    Як бухгалтер, нам потрібно відстежувати зміни в реальному часі
    """
    keys_to_delete = []

    # Завжди очищуємо загальні звіти при зміні лідів
    keys_to_delete.extend([
        "funnel_None_None_None",
        "managers_list",
    ])

    # Очищуємо кеш воронки для конкретного менеджера
    if manager_id:
        keys_to_delete.append(f"funnel_None_None_{manager_id}")

    # Очищуємо кеш платежів для конкретного ліду
    if lead_id:
        keys_to_delete.append(f"lead_payments_{lead_id}")

    # Очищуємо кеш звітів (використовуємо шаблон)
    cache.delete_many(keys_to_delete)

    # Очищуємо кеш по шаблонах (для звітів з датами)
    try:
        cache.delete_pattern("funnel_*")
        cache.delete_pattern("leads_report_*")
        cache.delete_pattern("detailed_report_*")
        cache.delete_pattern("payments_*")
    except AttributeError:
        # Якщо backend не підтримує delete_pattern
        pass


# 🚀 УТИЛІТА ДЛЯ СТАНДАРТИЗАЦІЇ ВІДПОВІДЕЙ
def api_response(data=None, meta=None, message=None, errors=None, status_code=200):
    """
    Стандартизована функція для API відповідей

    Args:
        data: Основні дані відповіді
        meta: Метадані (пагінація, статистика тощо)
        message: Повідомлення для користувача
        errors: Помилки валідації
        status_code: HTTP статус код
    """
    response_data = {
        "data": data or {},
        "meta": meta or {}
    }

    # Додаємо повідомлення в meta якщо є
    if message:
        response_data["meta"]["message"] = message

    # Додаємо помилки в meta якщо є
    if errors:
        response_data["meta"]["errors"] = errors

    return Response(response_data, status=status_code)


# 🚀 ОНОВЛЕНИЙ PING ENDPOINT
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ping(request):
    """🏓 Перевірка стану системи та з'єднання"""

    # Перевіряємо стан різних компонентів системи
    system_status = {
        "api_status": "online",
        "user": {
            "id": request.user.id,
            "username": request.user.username,
            "is_authenticated": True,
            "permissions": list(request.user.user_permissions.values_list("codename", flat=True))[:5]
        },
        "database_status": "connected",
        "cache_status": "unknown"
    }

    # Перевіряємо підключення до бази даних
    try:
        Lead.objects.count()
        system_status["database_status"] = "connected"
    except Exception as e:
        system_status["database_status"] = f"error: {str(e)}"

    # Перевіряємо кеш
    try:
        cache_test_key = "ping_test"
        cache.set(cache_test_key, "test_value", 5)
        if cache.get(cache_test_key) == "test_value":
            system_status["cache_status"] = "working"
            cache.delete(cache_test_key)
        else:
            system_status["cache_status"] = "not_working"
    except Exception as e:
        system_status["cache_status"] = f"error: {str(e)}"

    # Додаткова інформація про систему
    try:
        custom_user = CustomUser.objects.select_related('user').get(user=request.user)
        system_status["user"]["interface_type"] = custom_user.interface_type
    except CustomUser.DoesNotExist:
        system_status["user"]["interface_type"] = "default"

    return api_response(
        data=system_status,
        meta={
            "ping_time": timezone.now(),
            "server_time": timezone.now(),
            "response_time_ms": 1,  # Можна додати реальний підрахунок часу відповіді
            "system_uptime": "unknown",  # Можна додати реальний uptime
            "version": "1.0.0"
        },
        message=f"🏓 Pong! Привіт, {request.user.username}! Система працює нормально."
    )


def home(request):
    """🏠 Головна сторінка CRM системи"""

    # Базова статистика для головної сторінки
    context_data = {
        "system_info": {
            "name": "Nash CRM & ERP System",
            "version": "1.0.0",
            "environment": getattr(settings, 'ENVIRONMENT', 'production')
        },
        "user_info": None,
        "quick_stats": {}
    }

    # Якщо користувач авторизований - додаємо його дані
    if request.user.is_authenticated:
        try:
            custom_user = CustomUser.objects.select_related('user').get(user=request.user)
            interface_type = custom_user.interface_type
        except CustomUser.DoesNotExist:
            interface_type = 'default'

        context_data["user_info"] = {
            "username": request.user.username,
            "full_name": f"{request.user.first_name} {request.user.last_name}".strip(),
            "email": request.user.email,
            "interface_type": interface_type,
            "is_staff": request.user.is_staff,
            "last_login": request.user.last_login
        }

        # Швидка статистика для авторизованих користувачів
        if request.user.is_staff:
            try:
                today = timezone.now().date()
                context_data["quick_stats"] = {
                    "leads_today": Lead.objects.filter(created_at__date=today).count(),
                    "total_clients": Client.objects.count(),
                    "pending_tasks": ClientTask.objects.filter(
                        status__in=['pending', 'in_progress'],
                        assigned_to=request.user
                    ).count() if hasattr(ClientTask, 'assigned_to') else 0
                }
            except:
                context_data["quick_stats"] = {}

    context_data["meta"] = {
        "page_loaded_at": timezone.now(),
        "user_agent": request.META.get('HTTP_USER_AGENT', ''),
        "ip_address": request.META.get('REMOTE_ADDR', ''),
        "session_key": request.session.session_key
    }

    return render(request, "base.html", {
        "page_data": context_data
    })


class MyTokenObtainPairView(TokenObtainPairView):
    """🔐 Отримання JWT токенів з розширеною інформацією"""
    serializer_class = MyTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        # Викликаємо батьківський метод
        response = super().post(request, *args, **kwargs)

        # Якщо помилка авторизації - повертаємо в стандартному форматі
        if response.status_code != 200:
            return api_response(
                errors={
                    "authentication_error": "Невірні облікові дані",
                    "details": response.data
                },
                meta={
                    "login_attempt_time": timezone.now(),
                    "ip_address": request.META.get('REMOTE_ADDR'),
                    "user_agent": request.META.get('HTTP_USER_AGENT', '')[:100]
                },
                status_code=response.status_code
            )

        raw_data = response.data

        # Розділяємо токени та інформацію про користувача
        tokens = {
            "access": raw_data.get("access"),
            "refresh": raw_data.get("refresh"),
        }

        user_info = {
            k: v for k, v in raw_data.items()
            if k not in ["access", "refresh"]
        }

        # 🚀 СТАНДАРТИЗОВАНИЙ ФОРМАТ
        response.data = api_response(
            data={
                "tokens": tokens,
                "user": user_info
            },
            meta={
                "login_time": timezone.now(),
                "token_type": "JWT",
                "access_token_expires_in": 3600,  # 1 година
                "refresh_token_expires_in": 86400,  # 24 години
                "authentication_method": "jwt_pair",
                "ip_address": request.META.get('REMOTE_ADDR'),
                "session_info": {
                    "session_key": request.session.session_key,
                    "is_new_session": request.session.is_empty()
                }
            },
            message=f"✅ Успішна авторизація користувача {user_info.get('username')}"
        ).data

        return response

class LoginView(APIView):
    """🔐 Стандартна авторизація з детальною відповіддю"""

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        # Валідація вхідних даних
        if not username or not password:
            return api_response(
                errors={
                    "validation_error": "Логін та пароль обов'язкові",
                    "missing_fields": {
                        "username": not username,
                        "password": not password
                    }
                },
                meta={
                    "login_attempt_time": timezone.now(),
                    "ip_address": request.META.get('REMOTE_ADDR')
                },
                status_code=400
            )

        # Спроба авторизації
        user = authenticate(username=username, password=password)
        if user is None:
            return api_response(
                errors={
                    "authentication_failed": "Невірний логін або пароль",
                    "attempted_username": username,
                    "security_note": "Спроба авторизації зафіксована"
                },
                meta={
                    "login_attempt_time": timezone.now(),
                    "ip_address": request.META.get('REMOTE_ADDR'),
                    "user_agent": request.META.get('HTTP_USER_AGENT', '')[:100],
                    "failed_login": True
                },
                status_code=401
            )

        # Генеруємо токени
        refresh = RefreshToken.for_user(user)

        # Отримуємо додаткову інформацію про користувача
        try:
            custom_user = CustomUser.objects.select_related('user').get(user=user)
            interface_type = custom_user.interface_type
            avatar_url = custom_user.avatar.url if custom_user.avatar else None
        except CustomUser.DoesNotExist:
            interface_type = "default"
            avatar_url = None

        # Групи та дозволи
        groups = list(user.groups.values_list("name", flat=True))
        permissions = list(user.user_permissions.values_list("codename", flat=True))

        # Формуємо дані користувача
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": f"{user.first_name} {user.last_name}".strip(),
            "interface_type": interface_type,
            "avatar_url": avatar_url,
            "groups": groups,
            "permissions": permissions,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "is_active": user.is_active,
            "last_login": user.last_login,
            "date_joined": user.date_joined,
        }

        # Токени
        tokens_data = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "token_type": "Bearer"
        }

        return api_response(
            data={
                "tokens": tokens_data,
                "user": user_data
            },
            meta={
                "login_time": timezone.now(),
                "session_expires_in": 86400,  # 24 години
                "authentication_method": "username_password",
                "ip_address": request.META.get('REMOTE_ADDR'),
                "user_agent": request.META.get('HTTP_USER_AGENT', '')[:100],
                "session_info": {
                    "session_key": request.session.session_key,
                    "is_new_session": request.session.is_empty()
                },
                "security_info": {
                    "last_login": user.last_login,
                    "login_count": getattr(user, 'login_count', 0) + 1,
                    "account_status": "active" if user.is_active else "inactive"
                }
            },
            message=f"✅ Ласкаво просимо, {user.first_name or user.username}!"
        )


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.select_related('assigned_to').order_by('-created_at')
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Фільтри
        temperature = self.request.query_params.get('temperature')
        akb_segment = self.request.query_params.get('akb_segment')
        assigned_to = self.request.query_params.get('assigned_to')

        if temperature:
            queryset = queryset.filter(temperature=temperature)
        if akb_segment:
            queryset = queryset.filter(akb_segment=akb_segment)
        if assigned_to:
            queryset = queryset.filter(assigned_to=assigned_to)

        return queryset

    def list(self, request, *args, **kwargs):
        """📋 Список клієнтів з фільтрацією та статистикою"""
        queryset = self.filter_queryset(self.get_queryset())

        # Пагінація
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)

            # Статистика по всьому датасету (не тільки по сторінці)
            full_stats = queryset.aggregate(
                total_clients=Count('id'),
                total_revenue=Sum('total_spent'),
                avg_ltv=Avg('total_spent'),
                total_orders=Sum('total_orders')
            )

            # Розподіл по температурі
            temp_distribution = queryset.values('temperature').annotate(
                count=Count('id')
            ).order_by('-count')

            return api_response(
                data=paginated_response.data['results'],
                meta={
                    "pagination": {
                        "count": paginated_response.data['count'],
                        "next": paginated_response.data['next'],
                        "previous": paginated_response.data['previous']
                    },
                    "filters_applied": {
                        "temperature": request.query_params.get('temperature'),
                        "akb_segment": request.query_params.get('akb_segment'),
                        "assigned_to": request.query_params.get('assigned_to')
                    },
                    "dataset_stats": {
                        "total_clients": full_stats['total_clients'],
                        "total_revenue": float(full_stats['total_revenue'] or 0),
                        "avg_ltv": float(full_stats['avg_ltv'] or 0),
                        "total_orders": full_stats['total_orders'] or 0,
                        "temperature_distribution": {
                            item['temperature']: item['count']
                            for item in temp_distribution
                        }
                    },
                    "generated_at": timezone.now()
                }
            )

        # Без пагінації
        serializer = self.get_serializer(queryset, many=True)

        full_stats = queryset.aggregate(
            total_clients=Count('id'),
            total_revenue=Sum('total_spent'),
            avg_ltv=Avg('total_spent')
        )

        return api_response(
            data=serializer.data,
            meta={
                "total_clients": len(serializer.data),
                "filters_applied": {
                    "temperature": request.query_params.get('temperature'),
                    "akb_segment": request.query_params.get('akb_segment'),
                    "assigned_to": request.query_params.get('assigned_to')
                },
                "stats": full_stats,
                "generated_at": timezone.now()
            }
        )

    def create(self, request, *args, **kwargs):
        """➕ Створення нового клієнта"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Перевіряємо дублікати по телефону
        phone = serializer.validated_data.get('phone')
        if phone:
            normalized_phone = Client.normalize_phone(phone)
            existing_client = Client.objects.filter(phone=normalized_phone).first()

            if existing_client:
                return api_response(
                    errors={
                        "duplicate_phone": "Клієнт з таким номером телефону вже існує",
                        "existing_client": {
                            "id": existing_client.id,
                            "name": existing_client.full_name,
                            "phone": existing_client.phone,
                            "created_at": existing_client.created_at
                        }
                    },
                    meta={
                        "duplicate_check": {
                            "original_phone": phone,
                            "normalized_phone": normalized_phone,
                            "check_time": timezone.now()
                        }
                    },
                    status_code=409
                )

        try:
            instance = serializer.save()
            smart_cache_invalidation()

            return api_response(
                data=serializer.data,
                meta={
                    "created": True,
                    "client_id": instance.id,
                    "creation_time": timezone.now(),
                    "cache_cleared": True,
                    "initial_temperature": getattr(instance, 'temperature', 'cold'),
                    "initial_segment": getattr(instance, 'akb_segment', 'new')
                },
                message=f"✅ Клієнта {instance.full_name} успішно створено",
                status_code=201
            )
        except Exception as e:
            return api_response(
                errors={
                    "creation_error": f"Помилка створення клієнта: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "attempted_data": request.data
                },
                status_code=500
            )

    def update(self, request, *args, **kwargs):
        """📝 Оновлення клієнта"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Зберігаємо старі дані для порівняння
        old_data = {
            'temperature': getattr(instance, 'temperature', None),
            'akb_segment': getattr(instance, 'akb_segment', None),
            'assigned_to': instance.assigned_to.username if instance.assigned_to else None
        }

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            updated_instance = serializer.save()
            smart_cache_invalidation()

            # Визначаємо що змінилось
            changes = {}
            if hasattr(updated_instance, 'temperature') and old_data['temperature'] != updated_instance.temperature:
                changes['temperature'] = {
                    'old': old_data['temperature'],
                    'new': updated_instance.temperature
                }

            if hasattr(updated_instance, 'akb_segment') and old_data['akb_segment'] != updated_instance.akb_segment:
                changes['akb_segment'] = {
                    'old': old_data['akb_segment'],
                    'new': updated_instance.akb_segment
                }

            new_assigned = updated_instance.assigned_to.username if updated_instance.assigned_to else None
            if old_data['assigned_to'] != new_assigned:
                changes['assigned_to'] = {
                    'old': old_data['assigned_to'],
                    'new': new_assigned
                }

            return api_response(
                data=serializer.data,
                meta={
                    "updated": True,
                    "client_id": updated_instance.id,
                    "update_time": timezone.now(),
                    "cache_cleared": True,
                    "partial_update": partial,
                    "changes_made": changes,
                    "total_changes": len(changes)
                },
                message=f"✅ Клієнта {updated_instance.full_name} успішно оновлено"
            )
        except Exception as e:
            return api_response(
                errors={
                    "update_error": f"Помилка оновлення клієнта: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "client_id": instance.id
                },
                status_code=500
            )

    def retrieve(self, request, *args, **kwargs):
        """👤 Детальна інформація про клієнта"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # Додаємо розширену інформацією
        extended_data = serializer.data

        # Статистика по лідах клієнта
        leads_stats = Lead.objects.filter(phone=instance.phone).aggregate(
            total_leads=Count('id'),
            completed_leads=Count('id', filter=Q(status='completed')),
            in_progress_leads=Count('id', filter=Q(status__in=['queued', 'in_work', 'preparation'])),
            total_lead_value=Sum('price', filter=Q(status='completed'))
        )

        # Останні взаємодії
        try:
            recent_interactions = ClientInteraction.objects.filter(
                client=instance
            ).order_by('-created_at')[:3]
            interactions_data = [
                {
                    'id': i.id,
                    'type': i.interaction_type,
                    'subject': i.subject,
                    'outcome': i.outcome,
                    'created_at': i.created_at
                }
                for i in recent_interactions
            ]
        except:
            interactions_data = []

        # Активні задачі
        try:
            active_tasks = ClientTask.objects.filter(
                client=instance,
                status__in=['pending', 'in_progress']
            ).count()
        except:
            active_tasks = 0

        extended_data['analytics'] = {
            'leads_summary': {
                'total_leads': leads_stats['total_leads'],
                'completed_leads': leads_stats['completed_leads'],
                'in_progress_leads': leads_stats['in_progress_leads'],
                'total_value': float(leads_stats['total_lead_value'] or 0),
                'conversion_rate': round(
                    (leads_stats['completed_leads'] / leads_stats['total_leads'] * 100), 1
                ) if leads_stats['total_leads'] > 0 else 0
            },
            'engagement': {
                'recent_interactions': interactions_data,
                'active_tasks': active_tasks,
                'last_contact': getattr(instance, 'last_contact_date', None)
            },
            'financial': {
                'total_spent': float(getattr(instance, 'total_spent', 0) or 0),
                'total_orders': getattr(instance, 'total_orders', 0) or 0,
                'avg_order_value': float(getattr(instance, 'avg_check', 0) or 0),
                'ltv': float(getattr(instance, 'customer_lifetime_value', 0) or 0)
            }
        }

        return api_response(
            data=extended_data,
            meta={
                "client_id": instance.id,
                "data_includes": ["basic_info", "leads_summary", "engagement", "financial"],
                "analytics_generated_at": timezone.now(),
                "comprehensive_view": True
            }
        )

    def destroy(self, request, *args, **kwargs):
        """🗑️ Видалення клієнта"""
        instance = self.get_object()

        # Перевіряємо чи немає активних лідів
        active_leads = Lead.objects.filter(
            phone=instance.phone,
            status__in=['queued', 'in_work', 'preparation', 'on_the_way']
        )

        if active_leads.exists():
            return api_response(
                errors={
                    "deletion_blocked": f"Неможливо видалити клієнта з активними лідами",
                    "active_leads_count": active_leads.count(),
                    "active_leads": [
                        {
                            "id": lead.id,
                            "status": lead.status,
                            "created_at": lead.created_at
                        }
                        for lead in active_leads[:5]  # Показуємо перші 5
                    ],
                    "solution": "Спочатку завершіть або скасуйте активні ліди"
                },
                meta={
                    "client_id": instance.id,
                    "client_name": instance.full_name,
                    "check_time": timezone.now()
                },
                status_code=422
            )

        try:
            client_info = {
                "id": instance.id,
                "name": instance.full_name,
                "phone": instance.phone,
                "total_spent": float(getattr(instance, 'total_spent', 0) or 0),
                "total_orders": getattr(instance, 'total_orders', 0) or 0
            }

            # Видаляємо
            instance.delete()
            smart_cache_invalidation()

            return api_response(
                data={
                    "deleted_client": client_info
                },
                meta={
                    "deleted": True,
                    "deletion_time": timezone.now(),
                    "cache_cleared": True,
                    "cleanup_performed": True
                },
                message=f"✅ Клієнта {client_info['name']} успішно видалено",
                status_code=200
            )
        except Exception as e:
            return api_response(
                errors={
                    "deletion_error": f"Помилка видалення клієнта: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "client_id": instance.id
                },
                status_code=500
            )

    @action(detail=False, methods=['get'], url_path='leads/(?P<client_id>[^/.]+)')
    def leads(self, request, client_id=None):
        """GET /api/clients/leads/{id}/"""
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return api_response(
                errors={'client': 'Клієнт не знайдено'},
                status_code=404
            )

        cache_key = f"client_leads_{client.id}"
        cached_result = cache.get(cache_key)

        if cached_result is None:
            leads = Lead.objects.select_related('assigned_to').filter(phone=client.phone)
            cached_result = [
                {
                    "id": lead.id,
                    "full_name": lead.full_name,
                    "status": lead.status,
                    "price": float(lead.price or 0),
                    "created_at": lead.created_at,
                    "assigned_to": lead.assigned_to.username if lead.assigned_to else None
                } for lead in leads
            ]
            cache.set(cache_key, cached_result, 30)

        return api_response(
            data={
                'client': {
                    'id': client.id,
                    'name': client.full_name,
                    'phone': client.phone
                },
                'leads': cached_result
            },
            meta={
                'total_leads': len(cached_result),
                'cache_hit': cached_result == cache.get(cache_key),
                'cache_expires_in': 30,
                'data_includes': ['lead_basic_info', 'status', 'price', 'assignment']
            }
        )

    @action(detail=False, methods=['get'], url_path='payments/(?P<client_id>[^/.]+)')
    def payments(self, request, client_id=None):
        """GET /api/clients/payments/{id}/"""
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return api_response(
                errors={'client': 'Клієнт не знайдено'},
                status_code=404
            )

        cache_key = f"client_payments_{client.id}"
        cached_result = cache.get(cache_key)

        if cached_result is None:
            payments = LeadPaymentOperation.objects.select_related('lead').filter(
                lead__phone=client.phone
            ).order_by('-created_at')

            cached_result = [
                {
                    "id": p.id,
                    "lead_id": p.lead_id,
                    "type": p.operation_type,
                    "amount": float(p.amount),
                    "comment": p.comment,
                    "created_at": p.created_at,
                } for p in payments
            ]
            cache.set(cache_key, cached_result, 30)

        total_received = sum(p['amount'] for p in cached_result if p['type'] == 'received')
        total_expected = sum(p['amount'] for p in cached_result if p['type'] == 'expected')

        return api_response(
            data={
                'client': {
                    'id': client.id,
                    'name': client.full_name,
                    'phone': client.phone
                },
                'payments': cached_result
            },
            meta={
                'financial_summary': {
                    'total_payments': len(cached_result),
                    'total_received': total_received,
                    'total_expected': total_expected,
                    'balance': total_received - total_expected,
                    'payment_ratio': round((total_received / total_expected * 100), 1) if total_expected > 0 else 0
                },
                'cache_expires_in': 30,
                'generated_at': timezone.now()
            }
        )

    @action(detail=False, methods=['get'], url_path='temperature-stats')
    def temperature_stats(self, request):
        """GET /api/clients/temperature-stats/"""
        cache_key = "temperature_stats"
        cached_result = cache.get(cache_key)

        if cached_result is None:
            if not hasattr(Client, 'temperature'):
                return api_response(
                    errors={'temperature': 'Поле temperature не існує в моделі Client'},
                    status_code=400
                )

            stats = Client.objects.values('temperature').annotate(
                count=Count('id'),
                total_spent=Sum('total_spent'),
                avg_check=Avg('avg_check')
            ).order_by('temperature')

            result = {}
            for stat in stats:
                temp = stat['temperature']
                result[temp] = {
                    'count': stat['count'],
                    'total_spent': float(stat['total_spent'] or 0),
                    'avg_check': float(stat['avg_check'] or 0),
                    'label': dict(Client.TEMPERATURE_CHOICES).get(temp, temp) if hasattr(Client,
                                                                                         'TEMPERATURE_CHOICES') else temp
                }

            cache.set(cache_key, result, 300)
            cached_result = result

        return api_response(
            data=cached_result,
            meta={
                'analysis_type': 'temperature_segmentation',
                'total_segments': len(cached_result),
                'cache_expires_in': 300,
                'generated_at': timezone.now(),
                'business_insights': {
                    'most_valuable_segment': max(cached_result.items(), key=lambda x: x[1]['total_spent'])[
                        0] if cached_result else None,
                    'largest_segment': max(cached_result.items(), key=lambda x: x[1]['count'])[
                        0] if cached_result else None
                }
            }
        )

    @action(detail=False, methods=['get'], url_path='akb-segments')
    def akb_segments(self, request):
        """GET /api/clients/akb-segments/"""
        cache_key = "akb_segments_stats"
        cached_result = cache.get(cache_key)

        if cached_result is None:
            stats = Client.objects.filter(
                akb_segment__in=['vip', 'premium', 'standard', 'basic']
            ).values('akb_segment').annotate(
                count=Count('id'),
                total_revenue=Sum('total_spent'),
                avg_ltv=Avg('total_spent')
            ).order_by('-total_revenue')

            segments = list(stats)
            cache.set(cache_key, segments, 300)
            cached_result = segments

        total_akb_clients = sum(s['count'] for s in cached_result)
        total_akb_revenue = sum(float(s['total_revenue'] or 0) for s in cached_result)

        return api_response(
            data={
                'segments': [
                    {
                        'segment': s['akb_segment'],
                        'count': s['count'],
                        'total_revenue': float(s['total_revenue'] or 0),
                        'avg_ltv': float(s['avg_ltv'] or 0),
                        'revenue_share': round((float(s['total_revenue'] or 0) / total_akb_revenue * 100),
                                               1) if total_akb_revenue > 0 else 0
                    }
                    for s in cached_result
                ]
            },
            meta={
                'analysis_type': 'akb_segmentation',
                'summary': {
                    'total_akb_clients': total_akb_clients,
                    'total_akb_revenue': total_akb_revenue,
                    'segments_analyzed': len(cached_result)
                },
                'cache_expires_in': 300,
                'analysis_date': timezone.now()
            }
        )

    @action(detail=False, methods=['get'], url_path='rfm-analysis')
    def rfm_analysis(self, request):
        """GET /api/clients/rfm-analysis/"""
        cache_key = "rfm_analysis"
        cached_result = cache.get(cache_key)

        if cached_result is None:
            top_clients = Client.objects.filter(
                total_orders__gt=0
            ).order_by('-total_spent')[:10]

            rfm_distribution = {}
            for client in Client.objects.filter(rfm_score__isnull=False):
                score = client.rfm_score
                if score not in rfm_distribution:
                    rfm_distribution[score] = 0
                rfm_distribution[score] += 1

            result = {
                'top_clients': [
                    {
                        'id': c.id,
                        'name': c.full_name,
                        'phone': c.phone,
                        'total_spent': float(getattr(c, 'total_spent', 0) or 0),
                        'rfm_score': getattr(c, 'rfm_score', ''),
                        'segment': getattr(c, 'akb_segment', ''),
                        'last_purchase': getattr(c, 'last_purchase_date', None)
                    }
                    for c in top_clients
                ],
                'rfm_distribution': rfm_distribution
            }

            cache.set(cache_key, result, 300)
            cached_result = result

        return api_response(
            data=cached_result,
            meta={
                'analysis_type': 'RFM',
                'metrics': {
                    'top_clients_count': len(cached_result['top_clients']),
                    'rfm_scores_analyzed': len(cached_result['rfm_distribution']),
                    'total_value_top_clients': sum(c['total_spent'] for c in cached_result['top_clients'])
                },
                'cache_expires_in': 300,
                'methodology': 'Recency, Frequency, Monetary analysis'
            }
        )

    @action(detail=False, methods=['get'], url_path='churn-risk')
    def churn_risk(self, request):
        """GET /api/clients/churn-risk/"""
        cache_key = "churn_risk_clients"
        cached_result = cache.get(cache_key)

        if cached_result is None:
            filters = Q(total_orders__gt=0)

            if hasattr(Client, 'temperature'):
                filters &= Q(temperature='sleeping')

            if hasattr(Client, 'rfm_recency'):
                filters |= Q(rfm_recency__gt=180)

            risky_clients = Client.objects.filter(filters).order_by('-total_spent')[:20]

            result = {
                'risky_clients': [
                    {
                        'id': c.id,
                        'name': c.full_name,
                        'phone': c.phone,
                        'last_purchase': getattr(c, 'last_purchase_date', None),
                        'days_since_purchase': getattr(c, 'rfm_recency', 0),
                        'total_spent': float(getattr(c, 'total_spent', 0) or 0),
                        'risk_level': getattr(c, 'risk_of_churn', 'unknown'),
                        'recommendation': getattr(c, 'next_contact_recommendation', 'Зв\'язатися з клієнтом'),
                        'priority_score': self._calculate_churn_priority(c)
                    }
                    for c in risky_clients
                ]
            }

            # Сортуємо по пріоритету
            result['risky_clients'].sort(key=lambda x: x['priority_score'], reverse=True)
            cache.set(cache_key, result, 300)
            cached_result = result

        return api_response(
            data=cached_result,
            meta={
                'analysis_type': 'churn_risk',
                'risk_assessment': {
                    'risky_clients_count': len(cached_result['risky_clients']),
                    'potential_revenue_at_risk': sum(c['total_spent'] for c in cached_result['risky_clients']),
                    'criteria': 'sleeping temperature OR 180+ days inactive',
                    'high_priority_clients': len(
                        [c for c in cached_result['risky_clients'] if c['priority_score'] > 80])
                },
                'cache_expires_in': 300,
                'generated_at': timezone.now()
            }
        )

    def _calculate_churn_priority(self, client):
        """Розрахунок пріоритету для чурн-ризику"""
        score = 0

        # Базовий рівень витрат
        total_spent = float(getattr(client, 'total_spent', 0) or 0)
        if total_spent > 10000:
            score += 50
        elif total_spent > 5000:
            score += 30
        elif total_spent > 1000:
            score += 15

        # Рецентність
        recency = getattr(client, 'rfm_recency', 0)
        if recency > 365:
            score += 30
        elif recency > 180:
            score += 20
        elif recency > 90:
            score += 10

        # Частота замовлень
        orders = getattr(client, 'total_orders', 0) or 0
        if orders > 5:
            score += 20
        elif orders > 2:
            score += 10

        return min(score, 100)  # Максимум 100

    @action(detail=False, methods=['get'], url_path='hot-leads')
    def hot_leads(self, request):
        """GET /api/clients/hot-leads/"""
        cache_key = "hot_leads_clients"
        cached_result = cache.get(cache_key)

        if cached_result is None:
            if hasattr(Client, 'temperature'):
                hot_clients = Client.objects.filter(
                    temperature='hot'
                ).order_by('-created_at')[:20]
            else:
                hot_clients = Client.objects.order_by('-created_at')[:20]

            result = {
                'hot_leads': [
                    {
                        'id': c.id,
                        'name': c.full_name,
                        'phone': c.phone,
                        'assigned_to': c.assigned_to.username if c.assigned_to else None,
                        'created_at': c.created_at,
                        'leads_count': Lead.objects.filter(phone=c.phone).count(),
                        'recommendation': getattr(c, 'next_contact_recommendation', 'Зв\'язатися з клієнтом'),
                        'urgency_level': self._calculate_urgency(c)
                    }
                    for c in hot_clients
                ]
            }

            # Сортуємо по терміновості
            result['hot_leads'].sort(key=lambda x: x['urgency_level'], reverse=True)
            cache.set(cache_key, result, 300)
            cached_result = result

        return api_response(
            data=cached_result,
            meta={
                'analysis_type': 'hot_leads',
                'urgency_metrics': {
                    'hot_leads_count': len(cached_result['hot_leads']),
                    'unassigned_count': len([l for l in cached_result['hot_leads'] if not l['assigned_to']]),
                    'critical_urgency': len([l for l in cached_result['hot_leads'] if l['urgency_level'] > 80]),
                    'avg_leads_per_client': sum(l['leads_count'] for l in cached_result['hot_leads']) / len(
                        cached_result['hot_leads']) if cached_result['hot_leads'] else 0
                },
                'temperature_filter': 'hot',
                'cache_expires_in': 300,
                'priority': 'urgent_contact_required',
                'generated_at': timezone.now()
            }
        )

    def _calculate_urgency(self, client):
        """Розрахунок рівня терміновості для гарячих лідів"""
        urgency = 50  # Базовий рівень

        # Якщо не призначений менеджер
        if not client.assigned_to:
            urgency += 30

        # Кількість лідів
        leads_count = Lead.objects.filter(phone=client.phone).count()
        if leads_count > 3:
            urgency += 20
        elif leads_count > 1:
            urgency += 10

        # Недавність створення
        hours_since_created = (timezone.now() - client.created_at).total_seconds() / 3600
        if hours_since_created < 24:
            urgency += 20
        elif hours_since_created < 72:
            urgency += 10

        return min(urgency, 100)

    @action(detail=False, methods=['get'], url_path='journey/(?P<client_id>[^/.]+)')
    def client_journey(self, request, client_id=None):
        """GET /api/clients/journey/{id}/"""
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return api_response(
                errors={'client': 'Клієнт не знайдено'},
                status_code=404
            )

        # Всі ліди клієнта
        leads = Lead.objects.filter(phone=client.phone).order_by('created_at')

        # Взаємодії
        try:
            interactions = ClientInteraction.objects.filter(
                client=client
            ).order_by('created_at')
        except:
            interactions = []

        # Платежі
        payments = LeadPaymentOperation.objects.filter(
            lead__phone=client.phone
        ).order_by('created_at')

        # Хронологія
        timeline = []

        for lead in leads:
            timeline.append({
                'type': 'lead',
                'date': lead.created_at,
                'title': f'Створено лід: {lead.full_name}',
                'details': {
                    'lead_id': lead.id,
                    'status': lead.status,
                    'price': float(lead.price or 0),
                    'source': getattr(lead, 'source', 'Невідомо'),
                    'assigned_to': lead.assigned_to.username if lead.assigned_to else None
                }
            })

        for interaction in interactions:
            timeline.append({
                'type': 'interaction',
                'date': interaction.created_at,
                'title': f'{interaction.get_interaction_type_display()}: {interaction.subject}',
                'details': {
                    'interaction_id': interaction.id,
                    'outcome': getattr(interaction, 'outcome', ''),
                    'description': getattr(interaction, 'description', ''),
                    'created_by': interaction.created_by.username if hasattr(interaction,
                                                                             'created_by') and interaction.created_by else None
                }
            })

        for payment in payments:
            timeline.append({
                'type': 'payment',
                'date': payment.created_at,
                'title': f'Платіж: {payment.amount} грн',
                'details': {
                    'payment_id': payment.id,
                    'lead_id': payment.lead_id,
                    'type': payment.operation_type,
                    'amount': float(payment.amount),
                    'comment': payment.comment
                }
            })

        timeline.sort(key=lambda x: x['date'])

        # Аналітика подорожі
        journey_analytics = {
            'customer_lifecycle': {
                'days_as_customer': (timezone.now() - client.created_at).days,
                'first_interaction': min([item['date'] for item in timeline]) if timeline else None,
                'last_interaction': max([item['date'] for item in timeline]) if timeline else None,
                'engagement_frequency': len(timeline) / max((timezone.now() - client.created_at).days, 1)
            },
            'touchpoints': {
                'total_touchpoints': len(timeline),
                'leads_created': len([t for t in timeline if t['type'] == 'lead']),
                'interactions_count': len([t for t in timeline if t['type'] == 'interaction']),
                'payments_count': len([t for t in timeline if t['type'] == 'payment'])
            },
            'financial_journey': {
                'total_payments': sum([float(t['details']['amount']) for t in timeline if t['type'] == 'payment']),
                'avg_payment': sum([float(t['details']['amount']) for t in timeline if t['type'] == 'payment']) / len(
                    [t for t in timeline if t['type'] == 'payment']) if [t for t in timeline if
                                                                         t['type'] == 'payment'] else 0
            }
        }

        return api_response(
            data={
                'client': {
                    'id': client.id,
                    'name': client.full_name,
                    'phone': client.phone,
                    'temperature': getattr(client, 'temperature', 'cold'),
                    'akb_segment': getattr(client, 'akb_segment', 'new'),
                    'total_spent': float(getattr(client, 'total_spent', 0) or 0),
                    'rfm_score': getattr(client, 'rfm_score', ''),
                    'created_at': client.created_at
                },
                'timeline': timeline,
                'summary': {
                    'total_leads': leads.count(),
                    'total_interactions': len(interactions),
                    'total_payments': payments.count(),
                    'customer_since': getattr(client, 'first_purchase_date', client.created_at),
                    'ltv': float(getattr(client, 'customer_lifetime_value', 0) or 0)
                },
                'analytics': journey_analytics
            },
            meta={
                'journey_events': len(timeline),
                'client_id': client.id,
                'analysis_type': 'customer_journey',
                'data_includes': ['timeline', 'summary', 'lifecycle_analytics'],
                'generated_at': timezone.now(),
                'comprehensive_analysis': True
            }
        )

    @action(detail=False, methods=['post'], url_path='update-temperature/(?P<client_id>[^/.]+)')
    def update_temperature(self, request, client_id=None):
        """POST /api/clients/update-temperature/{id}/"""
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            return api_response(
                errors={'client': 'Клієнт не знайдено'},
                status_code=404
            )

        new_temperature = request.data.get('temperature')
        update_reason = request.data.get('reason', 'Ручне оновлення')

        if not hasattr(client, 'temperature'):
            return api_response(
                errors={'temperature': 'Поле temperature не існує в моделі Client'},
                status_code=400
            )

        if not hasattr(Client, 'TEMPERATURE_CHOICES'):
            return api_response(
                errors={'choices': 'TEMPERATURE_CHOICES не визначені'},
                status_code=400
            )

        if new_temperature not in dict(Client.TEMPERATURE_CHOICES):
            available_options = [
                {'code': code, 'label': label}
                for code, label in Client.TEMPERATURE_CHOICES
            ]
            return api_response(
                errors={
                    'temperature': 'Неправильна температура',
                    'provided_value': new_temperature,
                    'available_options': available_options
                },
                status_code=400
            )

        old_temperature = client.temperature

        # Перевіримо чи це справді зміна
        if old_temperature == new_temperature:
            return api_response(
                data={
                    'client': {
                        'id': client.id,
                        'name': client.full_name,
                        'phone': client.phone,
                        'temperature': client.temperature
                    }
                },
                meta={
                    'no_change': True,
                    'current_temperature': old_temperature,
                    'check_time': timezone.now()
                },
                message=f'Температура вже встановлена як {old_temperature}'
            )

        try:
            client.temperature = new_temperature
            client.save()

            smart_cache_invalidation()

            # Логування зміни (якщо потрібно)
            temperature_change_log = {
                'client_id': client.id,
                'old_temperature': old_temperature,
                'new_temperature': new_temperature,
                'changed_by': request.user.username,
                'change_time': timezone.now(),
                'reason': update_reason
            }

            return api_response(
                data={
                    'client': {
                        'id': client.id,
                        'name': client.full_name,
                        'phone': client.phone,
                        'old_temperature': old_temperature,
                        'new_temperature': new_temperature,
                        'temperature_label': dict(Client.TEMPERATURE_CHOICES).get(new_temperature, new_temperature)
                    },
                    'change_log': temperature_change_log
                },
                meta={
                    'updated': True,
                    'update_time': timezone.now(),
                    'cache_cleared': True,
                    'changed_by': request.user.username,
                    'business_impact': self._get_temperature_impact(old_temperature, new_temperature)
                },
                message=f'✅ Температуру змінено: {old_temperature} → {new_temperature}'
            )
        except Exception as e:
            return api_response(
                errors={
                    'update_error': f'Помилка оновлення температури: {str(e)}',
                    'details': str(e)
                },
                meta={
                    'error_time': timezone.now(),
                    'client_id': client.id,
                    'attempted_change': f'{old_temperature} → {new_temperature}'
                },
                status_code=500
            )

    def _get_temperature_impact(self, old_temp, new_temp):
        """Аналіз бізнес-впливу зміни температури"""
        temp_hierarchy = {'cold': 1, 'warm': 2, 'hot': 3, 'loyal': 4, 'sleeping': 0}

        old_level = temp_hierarchy.get(old_temp, 1)
        new_level = temp_hierarchy.get(new_temp, 1)

        if new_level > old_level:
            return {
                'type': 'positive',
                'description': 'Підвищення температури - клієнт стає більш активним',
                'recommendation': 'Збільшити інтенсивність комунікації'
            }
        elif new_level < old_level:
            return {
                'type': 'negative',
                'description': 'Зниження температури - ризик втрати клієнта',
                'recommendation': 'Розробити план реактивації'
            }
        else:
            return {
                'type': 'neutral',
                'description': 'Зміна температури в межах однакового рівня активності',
                'recommendation': 'Продовжити поточну стратегію'
            }

# 🚀 ФУНКЦІЯ ПЕРЕВІРКИ ДУБЛІКАТІВ
def check_duplicate_lead(phone, full_name=None, order_number=None, time_window_minutes=30):
    """
    Перевіряє чи є лід дублікатом за останні X хвилин
    """
    from django.utils import timezone
    from datetime import timedelta

    if not phone:
        return False, None

    # Нормалізуємо телефон
    normalized_phone = Client.normalize_phone(phone)

    # Час для перевірки (за останні 30 хвилин)
    time_threshold = timezone.now() - timedelta(minutes=time_window_minutes)

    # Базовий пошук по телефону + часу
    recent_leads = Lead.objects.filter(
        phone=normalized_phone,
        created_at__gte=time_threshold
    ).order_by('-created_at')

    if not recent_leads.exists():
        return False, None

    # Якщо є номер замовлення - строга перевірка
    if order_number:
        exact_match = recent_leads.filter(order_number=order_number).first()
        if exact_match:
            return True, exact_match

    # Якщо є ім'я - перевіряємо ім'я + телефон
    if full_name:
        name_match = recent_leads.filter(full_name__iexact=full_name.strip()).first()
        if name_match:
            return True, name_match

    # Якщо тільки телефон за останні 5 хвилин - теж дублікат
    very_recent = recent_leads.filter(
        created_at__gte=timezone.now() - timedelta(minutes=5)
    ).first()

    if very_recent:
        return True, very_recent

    return False, None


class ExternalLeadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        print(f"📥 API: Отримано запит на створення ліда: {request.data}")

        serializer = ExternalLeadSerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data.get('phone')
            full_name = serializer.validated_data.get('full_name')
            order_number = serializer.validated_data.get('order_number')

            is_duplicate, existing_lead = check_duplicate_lead(
                phone=phone,
                full_name=full_name,
                order_number=order_number,
                time_window_minutes=30
            )

            if is_duplicate:
                print(f"🚫 ДУБЛІКАТ! Знайдено існуючий лід #{existing_lead.id}")
                return api_response(
                    errors={
                        "type": "DUPLICATE_LEAD",
                        "message": f"Лід з таким номером телефону вже існує",
                        "existing_lead": {
                            "id": existing_lead.id,
                            "full_name": existing_lead.full_name,
                            "phone": existing_lead.phone,
                            "created_at": existing_lead.created_at,
                            "status": existing_lead.status
                        },
                        "duplicate_check": {
                            "phone": phone,
                            "normalized_phone": Client.normalize_phone(phone) if phone else None,
                            "full_name": full_name,
                            "time_window": "30 minutes"
                        }
                    },
                    status_code=status.HTTP_409_CONFLICT
                )

            print(f"✅ Не дублікат - створюємо новий лід")
            lead, context = create_lead_with_logic(serializer.validated_data)

            smart_cache_invalidation(
                lead_id=lead.id,
                manager_id=lead.assigned_to.id if lead.assigned_to else None
            )

            return api_response(
                data={
                    "lead": {
                        "id": lead.id,
                        "full_name": lead.full_name,
                        "phone": lead.phone,
                        "status": context['final_status'],
                        "assigned_manager": context['assigned_to'],
                        "created_at": lead.created_at,
                    }
                },
                meta={
                    "created": True,
                    "details": context,
                    "processing_time": timezone.now()
                },
                message=f"✅ Лід створено для {lead.full_name} — статус: {context['final_status'].upper()}",
                status_code=status.HTTP_201_CREATED
            )

        return api_response(
            errors={
                "type": "VALIDATION_ERROR",
                "details": serializer.errors
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def leads_report(request):
    """📊 Базовий звіт по лідах з фінансовою інформацією"""

    # 🛡️ ПЕРЕВІРКА ПРАВ АДМІНІСТРАТОРА
    if not request.user.is_staff:
        return api_response(
            errors={
                "permission_denied": "Доступ тільки для адміністраторів",
                "user_info": {
                    "username": request.user.username,
                    "is_staff": request.user.is_staff,
                    "is_authenticated": request.user.is_authenticated
                }
            },
            status_code=403
        )

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if not date_from or not date_to:
        return api_response(
            errors={"dates": "Потрібно вказати ?date_from=...&date_to=..."},
            status_code=400
        )

    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return api_response(
            errors={"date_format": "Невірний формат дати. Використовуйте YYYY-MM-DD"},
            status_code=400
        )

    cache_key = f"leads_report_{date_from}_{date_to}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return api_response(
            data=cached_result,
            meta={
                "cache_hit": True,
                "cache_expires_in": 60,
                "generated_at": timezone.now()
            }
        )

    leads = Lead.objects.filter(created_at__range=(start, end))
    status_counts = dict(leads.values('status').annotate(count=Count('id')).values_list('status', 'count'))

    payment_totals = LeadPaymentOperation.objects.filter(
        lead__created_at__range=(start, end)
    ).aggregate(
        expected_sum=Sum('amount', filter=Q(operation_type='expected')),
        received_sum=Sum('amount', filter=Q(operation_type='received'))
    )

    expected_sum = float(payment_totals['expected_sum'] or 0)
    received_sum = float(payment_totals['received_sum'] or 0)
    delta = expected_sum - received_sum

    result = {
        "period": {
            "date_from": date_from,
            "date_to": date_to
        },
        "summary": {
            "total_leads": leads.count(),
            "expected_sum": expected_sum,
            "received_sum": received_sum,
            "delta": delta
        },
        "by_status": status_counts
    }

    cache.set(cache_key, result, 60)

    return api_response(
        data=result,
        meta={
            "cache_hit": False,
            "cache_expires_in": 60,
            "generated_at": timezone.now(),
            "report_type": "leads_summary"
        }
    )


@staff_member_required
def leads_report_page(request):
    """📊 Сторінка звітів по лідах для адміністраторів"""

    form = LeadsReportForm(request.GET or None)

    # Базові дані для сторінки
    page_data = {
        "title": "Звіти по лідах",
        "user": {
            "username": request.user.username,
            "is_staff": request.user.is_staff,
            "is_superuser": request.user.is_superuser
        },
        "form_data": {
            "form_valid": form.is_valid() if form.is_bound else None,
            "has_data": bool(request.GET),
            "submitted_params": dict(request.GET) if request.GET else {}
        },
        "quick_stats": {},
        "available_filters": {
            "date_range": True,
            "manager_filter": True,
            "status_filter": True,
            "source_filter": True
        }
    }

    # Якщо форма валідна - додаємо швидку статистику
    if form.is_valid():
        try:
            # Базова статистика для показу на сторінці
            today = timezone.now().date()
            week_ago = today - timedelta(days=7)

            page_data["quick_stats"] = {
                "today_leads": Lead.objects.filter(created_at__date=today).count(),
                "week_leads": Lead.objects.filter(created_at__date__gte=week_ago).count(),
                "total_leads": Lead.objects.count(),
                "completed_today": Lead.objects.filter(
                    status='completed',
                    status_updated_at__date=today
                ).count()
            }

            # Статистика по статусах
            status_stats = Lead.objects.values('status').annotate(
                count=Count('id')
            ).order_by('-count')

            page_data["status_distribution"] = {
                stat['status']: stat['count'] for stat in status_stats
            }

            # Статистика по менеджерах
            manager_stats = Lead.objects.filter(
                assigned_to__isnull=False
            ).values(
                'assigned_to__username'
            ).annotate(
                total_leads=Count('id'),
                completed=Count('id', filter=Q(status='completed'))
            ).order_by('-total_leads')[:5]

            page_data["top_managers"] = list(manager_stats)

        except Exception as e:
            page_data["stats_error"] = f"Помилка завантаження статистики: {str(e)}"

    # Мета-інформація
    page_data["meta"] = {
        "page_loaded_at": timezone.now(),
        "form_errors": form.errors if form.errors else {},
        "available_reports": [
            "leads_summary",
            "manager_performance",
            "payment_analysis",
            "funnel_analytics"
        ],
        "export_formats": ["excel", "csv", "pdf"],
        "cache_info": {
            "reports_cached": True,
            "cache_duration": "60 seconds"
        }
    }

    # Додаємо повідомлення якщо є
    if form.is_valid() and request.GET:
        page_data["success_message"] = "Фільтри застосовано успішно"
    elif form.errors:
        page_data["error_message"] = "Перевірте правильність введених даних"

    context = {
        "form": form,
        "page_data": page_data
    }

    return render(request, "admin/reports/leads_report_form.html", context)


User = get_user_model()


class LeadsReportView(APIView):
    """📊 Детальний звіт по лідах з фінансовою аналітикою"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from = parse_date(request.GET.get('date_from'))
        date_to = parse_date(request.GET.get('date_to'))
        manager_id = request.GET.get('manager_id')

        # Валідація параметрів
        if not date_from and not date_to:
            # Якщо дати не вказані - беремо останні 30 днів
            date_to = timezone.now().date()
            date_from = date_to - timedelta(days=30)

        # 🚀 СКОРОЧУЄМО КЕШ до 2 хвилин для детального звіту
        cache_key = f"detailed_report_{date_from}_{date_to}_{manager_id}"
        cached_result = cache.get(cache_key)

        if cached_result:
            return api_response(
                data=cached_result,
                meta={
                    "cache_hit": True,
                    "cache_expires_in": 120,
                    "report_generated_at": timezone.now(),
                    "data_source": "cache"
                }
            )

        # Базовий QuerySet
        leads = Lead.objects.select_related('assigned_to')

        # Застосовуємо фільтри
        filters_applied = {}
        if date_from:
            leads = leads.filter(created_at__date__gte=date_from)
            filters_applied['date_from'] = str(date_from)
        if date_to:
            leads = leads.filter(created_at__date__lte=date_to)
            filters_applied['date_to'] = str(date_to)
        if manager_id:
            leads = leads.filter(assigned_to_id=manager_id)
            filters_applied['manager_id'] = manager_id

        now_date = now()

        # 📈 ЗВІТ ПО МЕНЕДЖЕРАХ
        managers_stats = leads.values(
            'assigned_to__id',
            'assigned_to__username'
        ).annotate(
            total_leads=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            in_work=Count('id', filter=Q(status='in_work')),
            queued=Count('id', filter=Q(status='queued')),
            declined=Count('id', filter=Q(status='declined')),
            total_price=Sum('price', filter=Q(status='completed')),
            avg_check=Avg('price', filter=Q(status='completed'))
        ).filter(assigned_to__isnull=False)

        managers_report = []
        for stat in managers_stats:
            conversion = round((stat['completed'] / stat['total_leads']) * 100, 1) if stat['total_leads'] else 0
            avg_check = round(float(stat['avg_check'] or 0), 2)

            # Розрахунок середнього часу обробки
            completed_leads = leads.filter(
                assigned_to__id=stat['assigned_to__id'],
                status='completed',
                status_updated_at__isnull=False
            ).annotate(
                duration=ExpressionWrapper(
                    F("status_updated_at") - F("created_at"),
                    output_field=DurationField()
                )
            ).values_list('duration', flat=True)

            durations = [d.total_seconds() for d in completed_leads if d]
            avg_minutes = int(sum(durations) / len(durations) / 60) if durations else None

            managers_report.append({
                "manager_id": stat['assigned_to__id'],
                "manager": stat['assigned_to__username'],
                "performance": {
                    "total_leads": stat['total_leads'],
                    "completed": stat['completed'],
                    "in_work": stat['in_work'],
                    "queued": stat['queued'],
                    "declined": stat['declined']
                },
                "financial": {
                    "total_revenue": float(stat['total_price'] or 0),
                    "avg_check": avg_check,
                    "conversion_rate": f"{conversion}%"
                },
                "efficiency": {
                    "avg_processing_time_minutes": avg_minutes,
                    "productivity_score": round(conversion * (avg_check / 1000), 1) if avg_check else 0
                }
            })

        # 💰 АНАЛІЗ БОРГІВ ПО КЛІЄНТАХ
        client_debts = Client.objects.annotate(
            total_price=Sum(
                'phone__price',
                filter=Q(phone__status='completed') & Q(phone__in=leads)
            ),
            total_received=Sum(
                'phone__payment_operations__amount',
                filter=Q(
                    phone__payment_operations__operation_type='received'
                ) & Q(phone__in=leads)
            )
        ).annotate(
            debt=F('total_price') - F('total_received')
        ).filter(debt__gt=0).values(
            'full_name', 'phone', 'debt', 'total_received', 'total_price'
        )

        clients_debt_report = [
            {
                "client_name": debt['full_name'],
                "phone": debt['phone'],
                "financial": {
                    "total_debt": float(debt['debt'] or 0),
                    "total_received": float(debt['total_received'] or 0),
                    "total_expected": float(debt['total_price'] or 0),
                    "payment_ratio": round(
                        (float(debt['total_received'] or 0) / float(debt['total_price'] or 1)) * 100, 1
                    )
                }
            }
            for debt in client_debts
        ]

        # Сортуємо по розміру боргу
        clients_debt_report.sort(key=lambda x: x['financial']['total_debt'], reverse=True)
        top_debtors = clients_debt_report[:10]

        # 📈 ВОРОНКА ПРОДАЖІВ
        funnel_data = leads.aggregate(
            queued=Count('id', filter=Q(status='queued')),
            in_work=Count('id', filter=Q(status='in_work')),
            awaiting_prepayment=Count('id', filter=Q(status='awaiting_prepayment')),
            preparation=Count('id', filter=Q(status='preparation')),
            warehouse_processing=Count('id', filter=Q(status='warehouse_processing')),
            warehouse_ready=Count('id', filter=Q(status='warehouse_ready')),
            on_the_way=Count('id', filter=Q(status='on_the_way')),
            completed=Count('id', filter=Q(status='completed')),
            declined=Count('id', filter=Q(status='declined'))
        )

        # 📊 СТАТИСТИКА ЗА ПЕРІОД
        period_stats = {
            "total_leads": leads.count(),
            "new_today": Lead.objects.filter(created_at__date=now_date.date()).count(),
            "completed_today": Lead.objects.filter(
                status='completed',
                status_updated_at__date=now_date.date()
            ).count(),
            "last_7_days": Lead.objects.filter(
                created_at__gte=now_date - timedelta(days=7)
            ).count(),
            "conversion_rate": round(
                (funnel_data['completed'] / leads.count() * 100), 1
            ) if leads.count() > 0 else 0
        }

        # 🚨 ПРОБЛЕМНІ ЛІДИ
        long_in_work_leads = Lead.objects.filter(
            status="in_work",
            created_at__lte=now_date - timedelta(days=1)
        ).values('id', 'full_name', 'created_at', 'assigned_to__username')

        paid_lead_ids = set(LeadPaymentOperation.objects.filter(
            operation_type='received'
        ).values_list('lead_id', flat=True))

        completed_without_payment = Lead.objects.filter(
            status="completed"
        ).exclude(id__in=paid_lead_ids).values('id', 'full_name', 'price', 'assigned_to__username')

        # Формуємо результат
        result = {
            "report_summary": {
                "period": filters_applied,
                "total_managers": len(managers_report),
                "total_debtors": len(clients_debt_report),
                "total_debt_amount": sum(d['financial']['total_debt'] for d in clients_debt_report)
            },
            "managers_performance": managers_report,
            "debt_analysis": {
                "all_debtors": clients_debt_report,
                "top_debtors": top_debtors,
                "debt_statistics": {
                    "total_debtors": len(clients_debt_report),
                    "largest_debt": max([d['financial']['total_debt'] for d in clients_debt_report], default=0),
                    "average_debt": round(
                        sum(d['financial']['total_debt'] for d in clients_debt_report) / len(clients_debt_report), 2
                    ) if clients_debt_report else 0
                }
            },
            "sales_funnel": funnel_data,
            "period_statistics": period_stats,
            "problem_leads": {
                "long_in_work": list(long_in_work_leads),
                "completed_without_payment": list(completed_without_payment),
                "delayed_count": len(long_in_work_leads),
                "unpaid_completed_count": len(completed_without_payment)
            }
        }

        # Кешуємо на 2 хвилини
        cache.set(cache_key, result, 120)

        return api_response(
            data=result,
            meta={
                "report_type": "detailed_leads_analysis",
                "filters_applied": filters_applied,
                "data_source": "database",
                "cache_expires_in": 120,
                "generated_at": timezone.now(),
                "processing_time": "real_time",
                "report_scope": {
                    "total_leads_analyzed": leads.count(),
                    "managers_included": len(managers_report),
                    "period_days": (date_to - date_from).days if date_from and date_to else None
                }
            }
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geocode_address(request):
    """🗺️ Геокодування адреси через Google Maps API"""
    address = request.query_params.get("address")
    if not address:
        return api_response(
            errors={"address": "Потрібно передати параметр ?address="},
            status_code=400
        )

    # Геокодування можна кешувати довго
    cache_key = f"geocode_{hash(address)}"
    cached_result = cache.get(cache_key)

    if cached_result:
        return api_response(
            data=cached_result,
            meta={
                "cache_hit": True,
                "cache_expires_in": 86400,
                "geocoding_service": "Google Maps API"
            }
        )

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": settings.GOOGLE_MAPS_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response_data = response.json()
    except requests.RequestException as e:
        return api_response(
            errors={"api_error": f"Помилка зв'язку з Google Maps API: {str(e)}"},
            status_code=500
        )

    if response_data.get("status") != "OK":
        return api_response(
            errors={
                "geocoding_error": "Нічого не знайдено або помилка Google Maps",
                "google_status": response_data.get("status"),
                "google_error": response_data.get("error_message", "")
            },
            status_code=400
        )

    result_data = response_data["results"][0]
    location = result_data["geometry"]["location"]
    components = {c['types'][0]: c['long_name'] for c in result_data['address_components']}

    geocoding_result = {
        "original_query": address,
        "formatted_address": result_data["formatted_address"],
        "coordinates": {
            "lat": location["lat"],
            "lng": location["lng"]
        },
        "address_components": {
            "country": components.get("country"),
            "city": components.get("locality") or components.get("administrative_area_level_1"),
            "postal_code": components.get("postal_code"),
            "street": components.get("route"),
            "street_number": components.get("street_number")
        },
        "place_id": result_data.get("place_id"),
        "geometry_type": result_data["geometry"]["location_type"]
    }

    cache.set(cache_key, geocoding_result, 86400)  # Кешуємо на день

    return api_response(
        data=geocoding_result,
        meta={
            "cache_hit": False,
            "cache_expires_in": 86400,
            "geocoding_service": "Google Maps API",
            "response_time": timezone.now(),
            "accuracy": result_data["geometry"]["location_type"]
        },
        message=f"Знайдено координати для: {result_data['formatted_address']}"
    )


@staff_member_required
def map_search_view(request):
    """🗺️ Сторінка пошуку на карті для адміністраторів"""

    # Перевіряємо чи є API ключ
    if not hasattr(settings, 'GOOGLE_MAPS_API_KEY') or not settings.GOOGLE_MAPS_API_KEY:
        context = {
            "error": "Google Maps API ключ не налаштований",
            "GOOGLE_MAPS_API_KEY": None,
            "page_data": {
                "title": "Помилка конфігурації",
                "error_type": "MISSING_API_KEY"
            }
        }
        return render(request, "admin/map_search_error.html", context)

    # Базовий контекст для карти
    context = {
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
        "page_data": {
            "title": "Пошук на карті",
            "user": {
                "username": request.user.username,
                "is_staff": request.user.is_staff,
                "is_superuser": request.user.is_superuser
            },
            "map_config": {
                "default_zoom": 10,
                "default_center": {
                    "lat": 49.8397,  # Львів
                    "lng": 24.0297
                },
                "search_enabled": True,
                "geocoding_enabled": True
            },
            "features": {
                "address_search": True,
                "coordinate_display": True,
                "place_details": True,
                "export_coordinates": True
            }
        },
        "meta": {
            "page_loaded_at": timezone.now(),
            "api_version": "v3",
            "language": "uk",
            "region": "UA"
        }
    }

    # Додаємо статистику якщо потрібно
    if request.GET.get('with_stats'):
        try:
            # Статистика по геокодуванню (якщо є кеш)
            geocoding_stats = {
                "total_requests": cache.get("geocoding_requests_count", 0),
                "cache_hits": cache.get("geocoding_cache_hits", 0),
                "last_request": cache.get("geocoding_last_request")
            }
            context["page_data"]["statistics"] = geocoding_stats
        except:
            pass

    return render(request, "admin/map_search.html", context)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def map_config_api(request):
    """🗺️ API для отримання конфігурації карти"""

    if not request.user.is_staff:
        return api_response(
            errors={"permission": "Доступ тільки для адміністраторів"},
            status_code=403
        )

    if not hasattr(settings, 'GOOGLE_MAPS_API_KEY') or not settings.GOOGLE_MAPS_API_KEY:
        return api_response(
            errors={
                "configuration": "Google Maps API ключ не налаштований",
                "solution": "Додайте GOOGLE_MAPS_API_KEY в settings.py"
            },
            status_code=500
        )

    config_data = {
        "api_key": settings.GOOGLE_MAPS_API_KEY,
        "map_settings": {
            "default_zoom": 10,
            "default_center": {
                "lat": 49.8397,  # Львів
                "lng": 24.0297
            },
            "language": "uk",
            "region": "UA"
        },
        "features": {
            "geocoding": True,
            "places": True,
            "streetview": True,
            "traffic": True
        },
        "limits": {
            "requests_per_day": 25000,
            "requests_per_minute": 300
        }
    }

    return api_response(
        data=config_data,
        meta={
            "config_loaded_at": timezone.now(),
            "user": request.user.username,
            "api_version": "v3"
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def funnel_data(request):
    date_from_raw = request.GET.get("from")
    date_to_raw = request.GET.get("to")
    manager_id = request.GET.get("manager_id")

    cache_key = f"funnel_{date_from_raw}_{date_to_raw}_{manager_id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return api_response(
            data=cached_result,
            meta={
                "cache_hit": True,
                "cache_expires_in": 30
            }
        )

    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None

    leads = Lead.objects.all()

    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)
    if manager_id:
        leads = leads.filter(assigned_to_id=manager_id)

    # 🆕 ОНОВЛЕНА ВОРОНКА З НОВИМ СТАТУСОМ
    funnel = leads.aggregate(
        queued=Count('id', filter=Q(status='queued')),
        in_work=Count('id', filter=Q(status='in_work')),
        awaiting_prepayment=Count('id', filter=Q(status='awaiting_prepayment')),
        preparation=Count('id', filter=Q(status='preparation')),
        warehouse_processing=Count('id', filter=Q(status='warehouse_processing')),
        warehouse_ready=Count('id', filter=Q(status='warehouse_ready')),  # 🆕 НОВИЙ СТАТУС
        on_the_way=Count('id', filter=Q(status='on_the_way')),
        completed=Count('id', filter=Q(status='completed')),
        declined=Count('id', filter=Q(status='declined'))
    )

    total_attempted = sum(funnel.values())
    conversion = round((funnel["completed"] / total_attempted) * 100, 1) if total_attempted > 0 else 0.0

    result = {
        "funnel": funnel,
        "warehouse_analytics": {
            "processing": funnel["warehouse_processing"],
            "ready": funnel["warehouse_ready"],
            "total_at_warehouse": funnel["warehouse_processing"] + funnel["warehouse_ready"],
            "warehouse_efficiency": round(
                (funnel["warehouse_ready"] / (funnel["warehouse_processing"] + funnel["warehouse_ready"]) * 100), 1
            ) if (funnel["warehouse_processing"] + funnel["warehouse_ready"]) > 0 else 0
        },
        "conversion_rate": f"{conversion}%"
    }

    cache.set(cache_key, result, 30)

    return api_response(
        data=result,
        meta={
            "filters": {
                "date_from": date_from_raw,
                "date_to": date_to_raw,
                "manager_id": manager_id
            },
            "total_leads": total_attempted,
            "cache_expires_in": 30,
            "generated_at": timezone.now(),
            "report_type": "funnel_analytics"
        }
    )


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.select_related('assigned_to').prefetch_related(
        Prefetch('payment_operations', queryset=LeadPaymentOperation.objects.order_by('-created_at'))
    ).order_by('-created_at')
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Фільтрація лідів"""
        queryset = super().get_queryset()

        # Фільтри
        status = self.request.query_params.get('status')
        assigned_to = self.request.query_params.get('assigned_to')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        phone = self.request.query_params.get('phone')

        if status:
            queryset = queryset.filter(status=status)
        if assigned_to:
            queryset = queryset.filter(assigned_to_id=assigned_to)
        if date_from:
            try:
                date_from_parsed = parse_date(date_from)
                if date_from_parsed:
                    queryset = queryset.filter(created_at__date__gte=date_from_parsed)
            except:
                pass
        if date_to:
            try:
                date_to_parsed = parse_date(date_to)
                if date_to_parsed:
                    queryset = queryset.filter(created_at__date__lte=date_to_parsed)
            except:
                pass
        if phone:
            normalized_phone = Client.normalize_phone(phone)
            queryset = queryset.filter(phone=normalized_phone)

        return queryset

    def list(self, request, *args, **kwargs):
        """📋 Список лідів з фільтрацією та статистикою"""
        queryset = self.filter_queryset(self.get_queryset())

        # Пагінація
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)

            # Статистика по всіх лідах (не тільки по сторінці)
            full_stats = queryset.aggregate(
                total_leads=Count('id'),
                completed_leads=Count('id', filter=Q(status='completed')),
                in_work_leads=Count('id', filter=Q(status='in_work')),
                total_revenue=Sum('price', filter=Q(status='completed')),
                avg_check=Avg('price', filter=Q(status='completed'))
            )

            # Розподіл по статусах
            status_distribution = queryset.values('status').annotate(
                count=Count('id')
            ).order_by('-count')

            return api_response(
                data=paginated_response.data['results'],
                meta={
                    "pagination": {
                        "count": paginated_response.data['count'],
                        "next": paginated_response.data['next'],
                        "previous": paginated_response.data['previous']
                    },
                    "filters_applied": {
                        "status": request.query_params.get('status'),
                        "assigned_to": request.query_params.get('assigned_to'),
                        "date_from": request.query_params.get('date_from'),
                        "date_to": request.query_params.get('date_to'),
                        "phone": request.query_params.get('phone')
                    },
                    "dataset_stats": {
                        "total_leads": full_stats['total_leads'],
                        "completed_leads": full_stats['completed_leads'],
                        "in_work_leads": full_stats['in_work_leads'],
                        "total_revenue": float(full_stats['total_revenue'] or 0),
                        "avg_check": float(full_stats['avg_check'] or 0),
                        "conversion_rate": round(
                            (full_stats['completed_leads'] / full_stats['total_leads'] * 100), 1
                        ) if full_stats['total_leads'] > 0 else 0,
                        "status_distribution": {
                            item['status']: item['count']
                            for item in status_distribution
                        }
                    },
                    "generated_at": timezone.now()
                }
            )

        # Без пагінації
        serializer = self.get_serializer(queryset, many=True)

        full_stats = queryset.aggregate(
            total_leads=Count('id'),
            total_revenue=Sum('price', filter=Q(status='completed'))
        )

        return api_response(
            data=serializer.data,
            meta={
                "total_leads": len(serializer.data),
                "filters_applied": {
                    "status": request.query_params.get('status'),
                    "assigned_to": request.query_params.get('assigned_to'),
                    "date_from": request.query_params.get('date_from'),
                    "date_to": request.query_params.get('date_to')
                },
                "stats": full_stats,
                "generated_at": timezone.now()
            }
        )

    def create(self, request, *args, **kwargs):
        """➕ Створення нового ліда"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Перевіряємо дублікати
        phone = serializer.validated_data.get('phone')
        full_name = serializer.validated_data.get('full_name')
        order_number = serializer.validated_data.get('order_number')

        if phone:
            is_duplicate, existing_lead = check_duplicate_lead(
                phone=phone,
                full_name=full_name,
                order_number=order_number
            )

            if is_duplicate:
                return api_response(
                    errors={
                        "duplicate_lead": "Знайдено дублікат ліда",
                        "existing_lead": {
                            "id": existing_lead.id,
                            "full_name": existing_lead.full_name,
                            "phone": existing_lead.phone,
                            "created_at": existing_lead.created_at,
                            "status": existing_lead.status
                        }
                    },
                    meta={
                        "duplicate_check": {
                            "phone": phone,
                            "normalized_phone": Client.normalize_phone(phone),
                            "check_time": timezone.now()
                        }
                    },
                    status_code=409
                )

        try:
            instance = serializer.save()
            smart_cache_invalidation(
                lead_id=instance.id,
                manager_id=instance.assigned_to.id if instance.assigned_to else None
            )

            return api_response(
                data=serializer.data,
                meta={
                    "created": True,
                    "lead_id": instance.id,
                    "creation_time": timezone.now(),
                    "cache_cleared": True,
                    "initial_status": instance.status,
                    "assigned_to": instance.assigned_to.username if instance.assigned_to else None
                },
                message=f"✅ Лід #{instance.id} для {instance.full_name} успішно створено",
                status_code=201
            )
        except Exception as e:
            return api_response(
                errors={
                    "creation_error": f"Помилка створення ліда: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "attempted_data": request.data
                },
                status_code=500
            )

    @action(detail=False, methods=['post'], url_path='upload-file/(?P<lead_id>[^/.]+)')
    def upload_file(self, request, lead_id=None):
        """📎 Завантаження файлів до ліда"""
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return api_response(
                errors={'lead': 'Лід не знайдено'},
                status_code=404
            )

        files = request.FILES.getlist('file')
        if not files:
            return api_response(
                errors={'files': 'Файли не передано'},
                status_code=400
            )

        uploaded_files = []
        for f in files:
            obj = LeadFile.objects.create(lead=lead, file=f)
            uploaded_files.append({
                "file_id": obj.id,
                "file_name": obj.file.name,
                "file_url": request.build_absolute_uri(obj.file.url),
                "uploaded_at": obj.uploaded_at
            })

        return api_response(
            data={
                'lead': {
                    'id': lead.id,
                    'full_name': lead.full_name
                },
                'uploaded_files': uploaded_files
            },
            meta={
                'files_count': len(uploaded_files),
                'upload_timestamp': timezone.now()
            },
            message=f'✅ Додано {len(uploaded_files)} файл(ів)'
        )

    @action(detail=False, methods=['get'], url_path='files/(?P<lead_id>[^/.]+)')
    def files(self, request, lead_id=None):
        """📁 Отримання файлів ліда"""
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return api_response(
                errors={'lead': 'Лід не знайдено'},
                status_code=404
            )

        files = lead.uploaded_files.all()
        files_list = [{
            "id": f.id,
            "name": f.file.name,
            "url": request.build_absolute_uri(f.file.url),
            "uploaded_at": f.uploaded_at,
        } for f in files]

        return api_response(
            data={
                'lead': {
                    'id': lead.id,
                    'full_name': lead.full_name
                },
                'files': files_list
            },
            meta={
                'total_files': len(files_list),
                'total_size_bytes': sum(f.file.size for f in files if f.file)
            }
        )

    @action(detail=False, methods=['get'], url_path='payments/(?P<lead_id>[^/.]+)')
    def payments(self, request, lead_id=None):
        """💰 Отримання платежів по ліду"""
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return api_response(
                errors={'lead': 'Лід не знайдено'},
                status_code=404
            )

        cache_key = f"lead_payments_{lead.id}"
        cached_payments = cache.get(cache_key)

        if cached_payments is None:
            payments = lead.payment_operations.all()
            cached_payments = [
                {
                    "id": p.id,
                    "type": p.operation_type,
                    "amount": float(p.amount),
                    "comment": p.comment,
                    "created_at": p.created_at,
                } for p in payments
            ]
            cache.set(cache_key, cached_payments, 30)

        total_expected = sum(p['amount'] for p in cached_payments if p['type'] == 'expected')
        total_received = sum(p['amount'] for p in cached_payments if p['type'] == 'received')

        return api_response(
            data={
                'lead': {
                    'id': lead.id,
                    'full_name': lead.full_name,
                    'price': float(lead.price or 0)
                },
                'payments': cached_payments
            },
            meta={
                'summary': {
                    'total_payments': len(cached_payments),
                    'total_expected': total_expected,
                    'total_received': total_received,
                    'balance': total_received - total_expected
                },
                'cache_hit': cached_payments == cache.get(cache_key),
                'cache_expires_in': 30
            }
        )

    @action(detail=False, methods=['post'], url_path='add-payment/(?P<lead_id>[^/.]+)')
    def add_payment(self, request, lead_id=None):
        """💰 Додавання платежу до ліда"""
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return api_response(
                errors={'lead': 'Лід не знайдено'},
                status_code=404
            )

        operation_type = request.data.get('operation_type')
        amount = request.data.get('amount')
        comment = request.data.get('comment', '')

        if not operation_type or not amount:
            return api_response(
                errors={
                    'required_fields': 'operation_type і amount обов\'язкові',
                    'example': {
                        'operation_type': 'received',
                        'amount': 1500,
                        'comment': 'Отримано від клієнта'
                    }
                },
                status_code=400
            )

        payment = LeadPaymentOperation.objects.create(
            lead=lead,
            operation_type=operation_type,
            amount=amount,
            comment=comment
        )

        smart_cache_invalidation(lead_id=lead.id)

        return api_response(
            data={
                'payment': {
                    'id': payment.id,
                    'type': payment.operation_type,
                    'amount': float(payment.amount),
                    'comment': payment.comment,
                    'created_at': payment.created_at,
                },
                'lead_payment_info': LeadStatusValidator.get_payment_info(lead)
            },
            meta={
                "payment_added": True,
                "lead_id": lead.id
            },
            message='✅ Платіж додано',
            status_code=201
        )

    def _get_last_activity_date(self, instance, payments):
        """Безпечне отримання дати останньої активності"""
        dates = [instance.created_at]

        # Додаємо дату оновлення статусу якщо є
        status_updated_at = getattr(instance, 'status_updated_at', None)
        if status_updated_at:
            dates.append(status_updated_at)

        # Додаємо дату останнього платежу якщо є
        if payments:
            dates.append(payments[0].created_at)

        # Фільтруємо None значення та повертаємо максимальну дату
        valid_dates = [d for d in dates if d is not None]
        return max(valid_dates) if valid_dates else instance.created_at

    @action(detail=False, methods=['put', 'patch'], url_path='update-status/(?P<lead_id>[^/.]+)')
    def update_status(self, request, lead_id=None):
        """🔄 Зміна статусу ліда з фінансовим контролем"""
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return api_response(
                errors={'lead': 'Лід не знайдено'},
                status_code=404
            )

        new_status = request.data.get('status')
        if not new_status:
            return api_response(
                errors={
                    'status': 'Потрібно вказати статус',
                    'available_statuses': LeadStatusValidator.get_allowed_transitions(lead.status, lead)
                },
                status_code=400
            )

        # Валідація через професійний валідатор
        validation = validate_lead_status_change(lead.id, new_status, request.user)

        if not validation['allowed']:
            return api_response(
                errors={
                    'status_change': validation['reason'],
                    'current_status': validation.get('current_status'),
                    'available_transitions': validation.get('available_transitions'),
                    'payment_info': validation.get('payment_info'),
                    'next_action': validation.get('next_action')
                },
                status_code=422
            )

        old_status = lead.status

        try:
            # Автоматичні фінансові операції при зміні статусів
            if new_status == "on_the_way" and old_status != "on_the_way":
                LeadPaymentOperation.objects.get_or_create(
                    lead=lead,
                    operation_type='expected',
                    defaults={
                        "amount": lead.price or 0,
                        "comment": f"Очікується повна оплата за лід #{lead.id}"
                    }
                )

            elif new_status == "completed":
                payment_info = LeadStatusValidator.get_payment_info(lead)
                if payment_info['shortage'] > 0:
                    return api_response(
                        errors={
                            'payment': f"Неможливо завершити - не вистачає {payment_info['shortage']} грн",
                            'payment_info': payment_info
                        },
                        status_code=422
                    )

            # Зміна статусу
            lead.status = new_status
            lead.status_updated_at = timezone.now()
            lead.save()

            smart_cache_invalidation(
                lead_id=lead.id,
                manager_id=lead.assigned_to.id if lead.assigned_to else None
            )

            return api_response(
                data={
                    'lead': {
                        'id': lead.id,
                        'full_name': lead.full_name,
                        'old_status': old_status,
                        'new_status': new_status,
                        'status_updated_at': lead.status_updated_at
                    },
                    'payment_info': LeadStatusValidator.get_payment_info(lead),
                    'next_action': LeadStatusValidator.get_next_required_action(lead)
                },
                meta={
                    "status_changed": True,
                    "change_timestamp": timezone.now()
                },
                message=f'✅ Статус змінено: {LeadStatusValidator.STATUS_NAMES.get(old_status)} → {LeadStatusValidator.STATUS_NAMES.get(new_status)}'
            )

        except Exception as e:
            return api_response(
                errors={
                    'exception': f'Помилка при зміні статусу: {str(e)}',
                    'details': str(e)
                },
                status_code=500
            )

    def update(self, request, *args, **kwargs):
        """📝 Оновлення ліда"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Зберігаємо старі дані для порівняння
        old_data = {
            'status': instance.status,
            'price': float(instance.price or 0),
            'assigned_to': instance.assigned_to.username if instance.assigned_to else None,
            'full_name': instance.full_name,
            'phone': instance.phone
        }

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            updated_instance = serializer.save()
            smart_cache_invalidation(
                lead_id=updated_instance.id,
                manager_id=updated_instance.assigned_to.id if updated_instance.assigned_to else None
            )

            # Визначаємо що змінилось
            changes = {}
            if old_data['status'] != updated_instance.status:
                changes['status'] = {
                    'old': old_data['status'],
                    'new': updated_instance.status
                }

            if old_data['price'] != float(updated_instance.price or 0):
                changes['price'] = {
                    'old': old_data['price'],
                    'new': float(updated_instance.price or 0)
                }

            new_assigned = updated_instance.assigned_to.username if updated_instance.assigned_to else None
            if old_data['assigned_to'] != new_assigned:
                changes['assigned_to'] = {
                    'old': old_data['assigned_to'],
                    'new': new_assigned
                }

            if old_data['full_name'] != updated_instance.full_name:
                changes['full_name'] = {
                    'old': old_data['full_name'],
                    'new': updated_instance.full_name
                }

            if old_data['phone'] != updated_instance.phone:
                changes['phone'] = {
                    'old': old_data['phone'],
                    'new': updated_instance.phone
                }

            return api_response(
                data=serializer.data,
                meta={
                    "updated": True,
                    "lead_id": updated_instance.id,
                    "update_time": timezone.now(),
                    "cache_cleared": True,
                    "partial_update": partial,
                    "changes_made": changes,
                    "total_changes": len(changes),
                    "payment_info": LeadStatusValidator.get_payment_info(updated_instance)
                },
                message=f"✅ Лід #{updated_instance.id} успішно оновлено"
            )
        except Exception as e:
            return api_response(
                errors={
                    "update_error": f"Помилка оновлення ліда: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "lead_id": instance.id
                },
                status_code=500
            )

    def retrieve(self, request, *args, **kwargs):
        """👤 Детальна інформація про лід"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # Додаємо розширену інформацію
        extended_data = serializer.data

        # Платіжна інформація
        payment_info = LeadStatusValidator.get_payment_info(instance)

        # Файли
        try:
            files = instance.uploaded_files.all()
            files_data = [
                {
                    'id': f.id,
                    'name': f.file.name,
                    'url': request.build_absolute_uri(f.file.url),
                    'uploaded_at': f.uploaded_at,
                    'size': f.file.size if f.file else 0
                }
                for f in files
            ]
        except:
            files_data = []

        # Історія платежів
        payments = instance.payment_operations.all()
        payments_data = [
            {
                'id': p.id,
                'type': p.operation_type,
                'amount': float(p.amount),
                'comment': p.comment,
                'created_at': p.created_at
            }
            for p in payments
        ]

        # Клієнт по телефону
        try:
            client = Client.objects.filter(phone=instance.phone).first()
            client_info = {
                'id': client.id,
                'full_name': client.full_name,
                'temperature': getattr(client, 'temperature', 'cold'),
                'akb_segment': getattr(client, 'akb_segment', 'new'),
                'total_spent': float(getattr(client, 'total_spent', 0) or 0),
                'total_orders': getattr(client, 'total_orders', 0) or 0
            } if client else None
        except:
            client_info = None

        # Доступні статуси
        available_statuses = LeadStatusValidator.get_allowed_transitions(instance.status, instance)

        extended_data['analytics'] = {
            'payment_info': {
                'price': float(payment_info['price']),
                'received': float(payment_info['received']),
                'shortage': float(payment_info['shortage']),
                'payment_percentage': payment_info['payment_percentage'],
                'is_fully_paid': LeadStatusValidator.is_fully_paid(instance),
                'payments_history': payments_data
            },
            'client_info': client_info,
            'files_info': {
                'total_files': len(files_data),
                'total_size_bytes': sum(f['size'] for f in files_data),
                'files': files_data
            },
            'status_info': {
                'current_status': instance.status,
                'status_name': LeadStatusValidator.STATUS_NAMES.get(instance.status),
                'available_transitions': available_statuses,
                'next_action': LeadStatusValidator.get_next_required_action(instance),
                'status_updated_at': getattr(instance, 'status_updated_at', None)
            },
            'timeline': {
                'created_at': instance.created_at,
                'days_since_creation': (timezone.now() - instance.created_at).days,
                'last_activity': self._get_last_activity_date(instance, payments)
            }
        }

        return api_response(
            data=extended_data,
            meta={
                "lead_id": instance.id,
                "data_includes": [
                    "basic_info", "payment_info", "client_info",
                    "files_info", "status_info", "timeline"
                ],
                "analytics_generated_at": timezone.now(),
                "comprehensive_view": True
            }
        )

    def destroy(self, request, *args, **kwargs):
        """🗑️ Видалення ліда"""
        instance = self.get_object()

        # Перевіряємо чи можна видаляти
        if instance.status in ['completed', 'on_the_way']:
            return api_response(
                errors={
                    "deletion_blocked": f"Неможливо видалити лід зі статусом '{instance.status}'",
                    "current_status": instance.status,
                    "reason": "Ліди в процесі доставки або завершені не можна видаляти",
                    "solution": "Змініть статус ліда або зверніться до адміністратора"
                },
                meta={
                    "lead_id": instance.id,
                    "lead_name": instance.full_name,
                    "check_time": timezone.now()
                },
                status_code=422
            )

        # Перевіряємо платежі
        payments = instance.payment_operations.filter(operation_type='received')
        if payments.exists():
            total_received = sum(float(p.amount) for p in payments)
            return api_response(
                errors={
                    "deletion_blocked": f"Неможливо видалити лід з платежами",
                    "total_received": total_received,
                    "payments_count": payments.count(),
                    "reason": "Лід має платежі, що надійшли",
                    "solution": "Спочатку оброб'іть всі платежі"
                },
                meta={
                    "lead_id": instance.id,
                    "check_time": timezone.now()
                },
                status_code=422
            )

        try:
            lead_info = {
                "id": instance.id,
                "full_name": instance.full_name,
                "phone": instance.phone,
                "status": instance.status,
                "price": float(instance.price or 0),
                "created_at": instance.created_at,
                "assigned_to": instance.assigned_to.username if instance.assigned_to else None
            }

            # Видаляємо файли
            files_deleted = 0
            try:
                for file_obj in instance.uploaded_files.all():
                    file_obj.file.delete()
                    file_obj.delete()
                    files_deleted += 1
            except:
                pass

            # Видаляємо лід
            instance.delete()
            smart_cache_invalidation()

            return api_response(
                data={
                    "deleted_lead": lead_info
                },
                meta={
                    "deleted": True,
                    "deletion_time": timezone.now(),
                    "cache_cleared": True,
                    "files_deleted": files_deleted,
                    "cleanup_performed": True
                },
                message=f"✅ Лід #{lead_info['id']} для {lead_info['full_name']} успішно видалено",
                status_code=200
            )
        except Exception as e:
            return api_response(
                errors={
                    "deletion_error": f"Помилка видалення ліда: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "lead_id": instance.id
                },
                status_code=500
            )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def all_payments(request):
    lead_id = request.GET.get("lead_id")
    client_id = request.GET.get("client_id")
    op_type = request.GET.get("type")

    cache_key = f"payments_{lead_id}_{client_id}_{op_type}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return api_response(
            data=cached_result,
            meta={
                "cache_hit": True,
                "cache_expires_in": 60
            }
        )

    payments = LeadPaymentOperation.objects.select_related('lead')

    if lead_id:
        payments = payments.filter(lead_id=lead_id)
    if client_id:
        payments = payments.filter(lead__phone__in=
                                   Client.objects.filter(id=client_id).values_list("phone", flat=True)
                                   )
    if op_type:
        payments = payments.filter(operation_type=op_type)

    payments_list = [
        {
            "id": p.id,
            "lead_id": p.lead_id,
            "type": p.operation_type,
            "amount": float(p.amount),
            "comment": p.comment,
            "created_at": p.created_at,
        } for p in payments.order_by("-created_at")
    ]

    # Підрахунки
    total_expected = sum(p['amount'] for p in payments_list if p['type'] == 'expected')
    total_received = sum(p['amount'] for p in payments_list if p['type'] == 'received')

    result = {
        "payments": payments_list
    }

    cache.set(cache_key, result, 60)

    return api_response(
        data=result,
        meta={
            "filters": {
                "lead_id": lead_id,
                "client_id": client_id,
                "operation_type": op_type
            },
            "summary": {
                "total_payments": len(payments_list),
                "total_expected": total_expected,
                "total_received": total_received,
                "balance": total_received - total_expected
            },
            "cache_expires_in": 60,
            "generated_at": timezone.now()
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_managers(request):
    cache_key = "managers_list"
    cached_result = cache.get(cache_key)

    if cached_result:
        return api_response(
            data=cached_result,
            meta={
                "cache_hit": True,
                "cache_expires_in": 120
            }
        )

    managers = CustomUser.objects.select_related('user').filter(interface_type='accountant')
    serializer = ManagerSerializer(managers, many=True, context={'request': request})

    cache.set(cache_key, serializer.data, 120)

    return api_response(
        data=serializer.data,
        meta={
            "total_managers": len(serializer.data),
            "cache_expires_in": 120,
            "generated_at": timezone.now()
        }
    )


class ManagerViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.select_related('user').filter(interface_type='accountant')
    serializer_class = ManagerSerializer
    permission_classes = [IsAuthenticated]

    # 🔧 ВИПРАВЛЕННЯ: Додаємо підтримку JSON + multipart
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # ← Додав JSONParser

    # Або ще краще - використовуємо стандартні парсери:
    # parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def list(self, request, *args, **kwargs):
        """📋 Список менеджерів з детальною статистикою"""
        queryset = self.filter_queryset(self.get_queryset())

        # Додаємо статистику по кожному менеджеру
        managers_with_stats = []
        for manager in queryset:
            serializer_data = ManagerSerializer(manager, context={'request': request}).data

            # Статистика по лідах
            leads_stats = Lead.objects.filter(assigned_to=manager.user).aggregate(
                total_leads=Count('id'),
                completed_leads=Count('id', filter=Q(status='completed')),
                in_work_leads=Count('id', filter=Q(status='in_work')),
                total_revenue=Sum('price', filter=Q(status='completed'))
            )

            # Додаємо статистику до даних менеджера
            serializer_data['performance'] = {
                'total_leads': leads_stats['total_leads'],
                'completed_leads': leads_stats['completed_leads'],
                'in_work_leads': leads_stats['in_work_leads'],
                'total_revenue': float(leads_stats['total_revenue'] or 0),
                'conversion_rate': round(
                    (leads_stats['completed_leads'] / leads_stats['total_leads'] * 100), 1
                ) if leads_stats['total_leads'] > 0 else 0
            }

            managers_with_stats.append(serializer_data)

        return api_response(
            data=managers_with_stats,
            meta={
                "total_managers": len(managers_with_stats),
                "active_managers": len([m for m in managers_with_stats if m['performance']['total_leads'] > 0]),
                "total_leads_managed": sum(m['performance']['total_leads'] for m in managers_with_stats),
                "generated_at": timezone.now(),
                "include_performance": True
            }
        )

    def create(self, request, *args, **kwargs):
        """➕ Створення нового менеджера"""
        # 🔍 ДІАГНОСТИКА: Логуємо що прийшло
        print(f"📥 ManagerViewSet.create: {request.content_type}")
        print(f"📊 Data: {request.data}")
        print(f"🎯 Parser: {type(request._request._stream)}")

        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            print(f"❌ Validation errors: {serializer.errors}")
            return api_response(
                errors={
                    "validation_errors": serializer.errors,
                    "received_data": dict(request.data),
                    "content_type": request.content_type
                },
                meta={
                    "error_type": "VALIDATION_ERROR",
                    "debug_info": {
                        "parser_classes": [p.__name__ for p in self.parser_classes],
                        "content_type": request.content_type,
                        "data_keys": list(request.data.keys()) if hasattr(request.data, 'keys') else 'no_keys'
                    }
                },
                status_code=400
            )

        try:
            instance = serializer.save()
            smart_cache_invalidation()

            return api_response(
                data=serializer.data,
                meta={
                    "created": True,
                    "manager_id": instance.id,
                    "creation_time": timezone.now(),
                    "cache_cleared": True,
                    "content_type_used": request.content_type
                },
                message=f"✅ Менеджера {instance.user.username} успішно створено",
                status_code=201
            )
        except Exception as e:
            print(f"❌ Creation error: {str(e)}")
            return api_response(
                errors={
                    "creation_error": f"Помилка створення менеджера: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "attempted_data": dict(request.data) if hasattr(request.data, 'items') else str(request.data)
                },
                status_code=500
            )

    def update(self, request, *args, **kwargs):
        """📝 Оновлення менеджера"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            old_data = {
                'username': instance.user.username,
                'interface_type': instance.interface_type
            }

            updated_instance = serializer.save()
            smart_cache_invalidation()

            return api_response(
                data=serializer.data,
                meta={
                    "updated": True,
                    "manager_id": updated_instance.id,
                    "update_time": timezone.now(),
                    "cache_cleared": True,
                    "partial_update": partial,
                    "old_data": old_data
                },
                message=f"✅ Менеджера {updated_instance.user.username} успішно оновлено"
            )
        except Exception as e:
            return api_response(
                errors={
                    "update_error": f"Помилка оновлення менеджера: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "manager_id": instance.id
                },
                status_code=500
            )

    def destroy(self, request, *args, **kwargs):
        """🗑️ Видалення менеджера"""
        instance = self.get_object()

        # Перевіряємо чи немає активних лідів
        active_leads_count = Lead.objects.filter(
            assigned_to=instance.user,
            status__in=['queued', 'in_work', 'preparation']
        ).count()

        if active_leads_count > 0:
            return api_response(
                errors={
                    "deletion_blocked": f"Неможливо видалити менеджера з {active_leads_count} активними лідами",
                    "active_leads": active_leads_count,
                    "solution": "Спочатку переназначте або завершіть активні ліди"
                },
                meta={
                    "manager_id": instance.id,
                    "manager_username": instance.user.username,
                    "check_time": timezone.now()
                },
                status_code=422
            )

        try:
            manager_info = {
                "id": instance.id,
                "username": instance.user.username,
                "email": instance.user.email,
                "interface_type": instance.interface_type
            }

            # Видаляємо
            instance.delete()
            smart_cache_invalidation()

            return api_response(
                data={
                    "deleted_manager": manager_info
                },
                meta={
                    "deleted": True,
                    "deletion_time": timezone.now(),
                    "cache_cleared": True
                },
                message=f"✅ Менеджера {manager_info['username']} успішно видалено",
                status_code=200
            )
        except Exception as e:
            return api_response(
                errors={
                    "deletion_error": f"Помилка видалення менеджера: {str(e)}",
                    "details": str(e)
                },
                meta={
                    "error_time": timezone.now(),
                    "manager_id": instance.id
                },
                status_code=500
            )

    def retrieve(self, request, *args, **kwargs):
        """👤 Детальна інформація про менеджера"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # Додаємо розширену статистику
        leads_stats = Lead.objects.filter(assigned_to=instance.user).aggregate(
            total_leads=Count('id'),
            completed_leads=Count('id', filter=Q(status='completed')),
            in_work_leads=Count('id', filter=Q(status='in_work')),
            queued_leads=Count('id', filter=Q(status='queued')),
            declined_leads=Count('id', filter=Q(status='declined')),
            total_revenue=Sum('price', filter=Q(status='completed')),
            avg_check=Avg('price', filter=Q(status='completed'))
        )

        # Статистика по місяцях (останні 6 місяців)
        monthly_stats = []
        for i in range(6):
            month_start = timezone.now().replace(day=1) - timedelta(days=30 * i)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            month_data = Lead.objects.filter(
                assigned_to=instance.user,
                created_at__date__range=[month_start.date(), month_end.date()]
            ).aggregate(
                leads=Count('id'),
                completed=Count('id', filter=Q(status='completed')),
                revenue=Sum('price', filter=Q(status='completed'))
            )

            monthly_stats.append({
                'month': month_start.strftime('%Y-%m'),
                'leads': month_data['leads'],
                'completed': month_data['completed'],
                'revenue': float(month_data['revenue'] or 0)
            })

        # Об'єднуємо дані
        response_data = serializer.data
        response_data['detailed_stats'] = {
            'overall': {
                'total_leads': leads_stats['total_leads'],
                'completed_leads': leads_stats['completed_leads'],
                'in_work_leads': leads_stats['in_work_leads'],
                'queued_leads': leads_stats['queued_leads'],
                'declined_leads': leads_stats['declined_leads'],
                'total_revenue': float(leads_stats['total_revenue'] or 0),
                'avg_check': float(leads_stats['avg_check'] or 0),
                'conversion_rate': round(
                    (leads_stats['completed_leads'] / leads_stats['total_leads'] * 100), 1
                ) if leads_stats['total_leads'] > 0 else 0
            },
            'monthly_performance': monthly_stats
        }

        return api_response(
            data=response_data,
            meta={
                "manager_id": instance.id,
                "data_includes": ["basic_info", "detailed_stats", "monthly_performance"],
                "stats_period": "6 months",
                "generated_at": timezone.now()
            }
        )


class CreateLeadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """📝 Створення нового ліда через API"""
        print(f"📥 CREATE API: Отримано запит: {request.data}")

        serializer = LeadSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                errors={
                    "validation_errors": serializer.errors,
                    "error_type": "SERIALIZER_VALIDATION"
                },
                status_code=400
            )

        order_number = serializer.validated_data.get('order_number')

        # 🛡️ ПЕРЕВІРКА ПО НОМЕРУ ЗАМОВЛЕННЯ
        if order_number:
            existing = Lead.objects.filter(order_number=order_number).first()
            if existing:
                print(f"🚫 ДУБЛІКАТ! Номер замовлення {order_number} вже є в ліді #{existing.id}")
                return api_response(
                    errors={
                        "duplicate_error": {
                            "type": "ORDER_NUMBER_EXISTS",
                            "message": f"Номер замовлення {order_number} вже використовується",
                            "existing_lead": {
                                "id": existing.id,
                                "full_name": existing.full_name,
                                "phone": existing.phone,
                                "created_at": existing.created_at,
                                "status": existing.status,
                                "assigned_to": existing.assigned_to.username if existing.assigned_to else None
                            }
                        }
                    },
                    meta={
                        "duplicate_check": {
                            "order_number": order_number,
                            "check_time": timezone.now(),
                            "existing_lead_id": existing.id
                        }
                    },
                    status_code=409
                )

        # Створюємо лід
        try:
            lead = serializer.save()
            print(f"✅ Створено лід #{lead.id} з номером замовлення {order_number}")

            # Очищуємо кеш
            smart_cache_invalidation(
                lead_id=lead.id,
                manager_id=lead.assigned_to.id if lead.assigned_to else None
            )

            lead_data = {
                "id": lead.id,
                "full_name": lead.full_name,
                "phone": lead.phone,
                "order_number": order_number,
                "status": lead.status,
                "price": float(lead.price or 0),
                "assigned_to": lead.assigned_to.username if lead.assigned_to else None,
                "created_at": lead.created_at,
                "source": getattr(lead, 'source', 'manual_creation')
            }

            return api_response(
                data={
                    "lead": lead_data
                },
                meta={
                    "created": True,
                    "creation_method": "manual_api",
                    "processing_time": timezone.now(),
                    "cache_cleared": True,
                    "lead_id": lead.id
                },
                message=f"✅ Лід #{lead.id} створено успішно для {lead.full_name}",
                status_code=201
            )

        except Exception as e:
            print(f"❌ Помилка створення ліда: {str(e)}")
            return api_response(
                errors={
                    "creation_error": {
                        "type": "DATABASE_ERROR",
                        "message": f"Не вдалося створити лід: {str(e)}",
                        "details": str(e)
                    }
                },
                meta={
                    "error_time": timezone.now(),
                    "attempted_data": serializer.validated_data
                },
                status_code=500
            )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_lead_duplicate(request):
    """
    🔍 Endpoint для перевірки чи є лід дублікатом БЕЗ створення
    """
    phone = request.data.get('phone')
    full_name = request.data.get('full_name')
    order_number = request.data.get('order_number')

    if not phone:
        return api_response(
            errors={"phone": "Телефон обов'язковий для перевірки дублікатів"},
            status_code=400
        )

    is_duplicate, existing_lead = check_duplicate_lead(
        phone=phone,
        full_name=full_name,
        order_number=order_number
    )

    normalized_phone = Client.normalize_phone(phone) if phone else None

    duplicate_check_data = {
        "is_duplicate": is_duplicate,
        "search_criteria": {
            "phone": phone,
            "normalized_phone": normalized_phone,
            "full_name": full_name,
            "order_number": order_number
        },
        "existing_lead": None
    }

    if existing_lead:
        duplicate_check_data["existing_lead"] = {
            "id": existing_lead.id,
            "full_name": existing_lead.full_name,
            "phone": existing_lead.phone,
            "order_number": getattr(existing_lead, 'order_number', None),
            "status": existing_lead.status,
            "created_at": existing_lead.created_at,
            "assigned_to": existing_lead.assigned_to.username if existing_lead.assigned_to else None,
            "price": float(existing_lead.price or 0)
        }

    meta_info = {
        "check_performed_at": timezone.now(),
        "check_method": "phone_name_order_combination",
        "time_window_checked": "30 minutes",
        "duplicate_found": is_duplicate
    }

    if is_duplicate:
        meta_info["duplicate_reason"] = "Знайдено лід з таким же телефоном та/або номером замовлення"
        meta_info["recommendation"] = "Використайте існуючий лід або змініть дані"
        message = f"⚠️ Знайдено дублікат! Лід #{existing_lead.id} вже існує"
    else:
        meta_info["recommendation"] = "Можна створювати новий лід"
        message = "✅ Дублікатів не знайдено, лід можна створювати"

    return api_response(
        data=duplicate_check_data,
        meta=meta_info,
        message=message
    )


class ClientInteractionViewSet(viewsets.ModelViewSet):
    serializer_class = ClientInteractionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ClientInteraction.objects.select_related(
            'client', 'created_by'
        ).order_by('-created_at')

        client_id = self.request.query_params.get('client_id')
        if client_id:
            queryset = queryset.filter(client_id=client_id)

        return queryset

    def list(self, request, *args, **kwargs):
        """Список взаємодій"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)

            return api_response(
                data=paginated_response.data['results'],
                meta={
                    "pagination": {
                        "count": paginated_response.data['count'],
                        "next": paginated_response.data['next'],
                        "previous": paginated_response.data['previous']
                    },
                    "total_interactions": queryset.count()
                }
            )

        serializer = self.get_serializer(queryset, many=True)
        return api_response(
            data=serializer.data,
            meta={
                "total_interactions": queryset.count(),
                "filtered_count": len(serializer.data)
            }
        )

    def create(self, request, *args, **kwargs):
        """Створення взаємодії"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        instance = serializer.save(created_by=request.user)

        # Оновлюємо дату останнього контакту з клієнтом
        client = instance.client
        client.last_contact_date = timezone.now()
        client.save()

        return api_response(
            data=serializer.data,
            meta={
                "created": True,
                "interaction_id": instance.id,
                "client_updated": True
            },
            message="Взаємодію успішно створено",
            status_code=status.HTTP_201_CREATED
        )


class ClientTaskViewSet(viewsets.ModelViewSet):
    serializer_class = ClientTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ClientTask.objects.select_related(
            'client', 'assigned_to'
        ).order_by('due_date')

        client_id = self.request.query_params.get('client_id')
        task_status = self.request.query_params.get('status')
        assigned_to_me = self.request.query_params.get('assigned_to_me')

        if client_id:
            queryset = queryset.filter(client_id=client_id)
        if task_status:
            queryset = queryset.filter(status=task_status)
        if assigned_to_me == 'true':
            queryset = queryset.filter(assigned_to=self.request.user)

        return queryset

    def list(self, request, *args, **kwargs):
        """Список задач"""
        queryset = self.filter_queryset(self.get_queryset())

        # Статистика по задачах
        overdue_count = queryset.filter(
            due_date__lt=timezone.now(),
            status__in=['pending', 'in_progress']
        ).count()

        urgent_count = queryset.filter(
            priority='urgent',
            status__in=['pending', 'in_progress']
        ).count()

        serializer = self.get_serializer(queryset, many=True)

        return api_response(
            data=serializer.data,
            meta={
                "total_tasks": queryset.count(),
                "overdue_tasks": overdue_count,
                "urgent_tasks": urgent_count,
                "filters_applied": {
                    "client_id": request.query_params.get('client_id'),
                    "status": request.query_params.get('status'),
                    "assigned_to_me": request.query_params.get('assigned_to_me')
                }
            }
        )

    def create(self, request, *args, **kwargs):
        """Створення задачі"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        instance = serializer.save()

        return api_response(
            data=serializer.data,
            meta={
                "created": True,
                "task_id": instance.id,
                "due_in_hours": (instance.due_date - timezone.now()).total_seconds() / 3600
            },
            message="Задачу успішно створено",
            status_code=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=['get'], url_path='my-tasks')
    def my_tasks(self, request):
        """GET /api/tasks/my-tasks/"""
        tasks = ClientTask.objects.filter(
            assigned_to=request.user,
            status__in=['pending', 'in_progress']
        ).order_by('due_date')[:10]

        tasks_data = [
            {
                'id': task.id,
                'title': task.title,
                'client_name': task.client.full_name,
                'client_phone': task.client.phone,
                'priority': task.priority,
                'due_date': task.due_date,
                'is_overdue': task.due_date < timezone.now()
            }
            for task in tasks
        ]

        return api_response(
            data={
                "tasks": tasks_data
            },
            meta={
                "user": request.user.username,
                "total_my_tasks": len(tasks_data),
                "overdue_count": sum(1 for task in tasks_data if task['is_overdue'])
            }
        )

    @action(detail=False, methods=['get'], url_path='overdue-tasks')
    def overdue_tasks(self, request):
        """GET /api/tasks/overdue-tasks/"""
        overdue = ClientTask.objects.filter(
            due_date__lt=timezone.now(),
            status__in=['pending', 'in_progress']
        ).order_by('due_date')

        overdue_data = [
            {
                'id': task.id,
                'title': task.title,
                'client_name': task.client.full_name,
                'assigned_to': task.assigned_to.username,
                'due_date': task.due_date,
                'days_overdue': (timezone.now() - task.due_date).days
            }
            for task in overdue
        ]

        return api_response(
            data={
                "overdue_tasks": overdue_data
            },
            meta={
                "total_overdue": len(overdue_data),
                "most_overdue_days": max((task['days_overdue'] for task in overdue_data), default=0)
            }
        )


# 🔥 НОВИЙ API ДЛЯ CRM ДАШБОРДУ
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def crm_dashboard(request):
    """🎯 Головний CRM дашборд"""
    cache_key = f"crm_dashboard_{request.user.id}"
    cached_result = cache.get(cache_key)

    if cached_result:
        return api_response(
            data=cached_result,
            meta={
                "cache_hit": True,
                "cache_expires_in": 300,
                "user_id": request.user.id
            }
        )

    # Статистика по клієнтах
    clients_stats = Client.objects.aggregate(
        total_clients=Count('id'),
        akb_clients=Count('id', filter=Q(total_orders__gt=0)),
        cold_leads=Count('id', filter=Q(temperature='cold')),
        warm_leads=Count('id', filter=Q(temperature='warm')),
        hot_leads=Count('id', filter=Q(temperature='hot')),
        sleeping_clients=Count('id', filter=Q(temperature='sleeping')),
        total_revenue=Sum('total_spent'),
        avg_ltv=Avg('total_spent', filter=Q(total_orders__gt=0))
    )

    # ТОП клієнти
    top_clients = Client.objects.filter(
        total_orders__gt=0
    ).order_by('-total_spent')[:5]

    # Ризикові клієнти
    churn_risk_clients = Client.objects.filter(
        Q(temperature='sleeping') | Q(rfm_recency__gt=180),
        total_orders__gt=0
    ).count()

    # Задачі що потребують уваги
    my_urgent_tasks = ClientTask.objects.filter(
        assigned_to=request.user,
        status__in=['pending', 'in_progress'],
        due_date__lte=timezone.now() + timedelta(days=1)
    ).count()

    # Конверсія по температурі
    temperature_conversion = {}
    for temp_code, temp_name in Client.TEMPERATURE_CHOICES:
        clients_count = Client.objects.filter(temperature=temp_code).count()
        if clients_count > 0:
            converted = Client.objects.filter(
                temperature=temp_code,
                total_orders__gt=0
            ).count()
            temperature_conversion[temp_code] = {
                'name': temp_name,
                'total': clients_count,
                'converted': converted,
                'conversion_rate': round((converted / clients_count) * 100, 1)
            }

    # Недавні взаємодії
    recent_interactions = ClientInteraction.objects.select_related(
        'client', 'created_by'
    ).order_by('-created_at')[:5]

    result = {
        'summary': {
            'total_clients': clients_stats['total_clients'],
            'akb_clients': clients_stats['akb_clients'],
            'hot_leads': clients_stats['hot_leads'],
            'churn_risk': churn_risk_clients,
            'total_revenue': float(clients_stats['total_revenue'] or 0),
            'avg_ltv': float(clients_stats['avg_ltv'] or 0),
            'urgent_tasks': my_urgent_tasks
        },
        'temperature_breakdown': {
            'cold': clients_stats['cold_leads'],
            'warm': clients_stats['warm_leads'],
            'hot': clients_stats['hot_leads'],
            'sleeping': clients_stats['sleeping_clients']
        },
        'temperature_conversion': temperature_conversion,
        'top_clients': [
            {
                'id': c.id,
                'name': c.full_name,
                'total_spent': float(c.total_spent),
                'segment': c.akb_segment,
                'rfm_score': c.rfm_score
            }
            for c in top_clients
        ],
        'recent_interactions': [
            {
                'id': i.id,
                'client_name': i.client.full_name,
                'type': i.interaction_type,
                'subject': i.subject,
                'outcome': i.outcome,
                'created_at': i.created_at,
                'created_by': i.created_by.username
            }
            for i in recent_interactions
        ]
    }

    cache.set(cache_key, result, 300)

    return api_response(
        data=result,
        meta={
            "dashboard_for": request.user.username,
            "cache_expires_in": 300,
            "generated_at": timezone.now(),
            "data_freshness": "5 minutes"
        }
    )


# 🔥 МАСОВЕ ОНОВЛЕННЯ МЕТРИК КЛІЄНТІВ
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_all_client_metrics(request):
    """🔄 Масове оновлення метрик всіх клієнтів"""
    if not request.user.is_staff:
        return api_response(
            errors={'permission': 'Тільки адміністратори можуть запускати масове оновлення'},
            status_code=403
        )

    updated_count = 0
    errors = []

    for client in Client.objects.all():
        try:
            client.update_client_metrics()
            updated_count += 1
        except Exception as e:
            errors.append(f"Клієнт {client.id}: {str(e)}")

    return api_response(
        data={
            "updated_count": updated_count,
            "errors": errors[:10]  # Показуємо перші 10 помилок
        },
        meta={
            "total_clients": Client.objects.count(),
            "success_rate": round((updated_count / Client.objects.count() * 100), 2),
            "update_timestamp": timezone.now()
        },
        message=f'Оновлено метрики для {updated_count} клієнтів'
    )


# 🔥 АВТОМАТИЧНЕ СТВОРЕННЯ ЗАДАЧ ПО КЛІЄНТАХ
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_follow_up_tasks(request):
    """📅 Автоматичне створення задач для follow-up"""

    # Клієнти що потребують реактивації
    sleeping_clients = Client.objects.filter(
        temperature='sleeping',
        total_orders__gt=0
    ).exclude(
        tasks__status__in=['pending', 'in_progress'],
        tasks__title__icontains='реактивація'
    )

    # Гарячі ліди що потребують уваги
    hot_leads = Client.objects.filter(
        temperature='hot'
    ).exclude(
        tasks__status__in=['pending', 'in_progress'],
        tasks__title__icontains='контакт'
    )

    created_tasks = []

    # Створюємо задачі для сплячих клієнтів
    for client in sleeping_clients:
        task = ClientTask.objects.create(
            client=client,
            title=f'Реактивація клієнта: {client.full_name}',
            description=f'Клієнт не купував {client.rfm_recency} днів. Загальна сума покупок: {client.total_spent} грн.',
            assigned_to=client.assigned_to or request.user,
            priority='medium',
            due_date=timezone.now() + timedelta(days=3)
        )
        created_tasks.append({
            'id': task.id,
            'type': 'reactivation',
            'title': task.title,
            'client': task.client.full_name,
            'priority': task.priority,
            'due_date': task.due_date
        })

    # Створюємо задачі для гарячих лідів
    for client in hot_leads:
        task = ClientTask.objects.create(
            client=client,
            title=f'ТЕРМІНОВИЙ контакт: {client.full_name}',
            description=f'Гарячий лід! {client.next_contact_recommendation}',
            assigned_to=client.assigned_to or request.user,
            priority='urgent',
            due_date=timezone.now() + timedelta(hours=24)
        )
        created_tasks.append({
            'id': task.id,
            'type': 'hot_lead',
            'title': task.title,
            'client': task.client.full_name,
            'priority': task.priority,
            'due_date': task.due_date
        })

    return api_response(
        data={
            "created_tasks": created_tasks
        },
        meta={
            "total_created": len(created_tasks),
            "sleeping_clients_tasks": len(sleeping_clients),
            "hot_leads_tasks": len(hot_leads),
            "creation_timestamp": timezone.now()
        },
        message=f'Створено {len(created_tasks)} нових задач'
    )


# 🔥 СЕГМЕНТАЦІЯ КЛІЄНТІВ ДЛЯ МАРКЕТИНГУ
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_segments_for_marketing(request):
    """🎯 Сегменти клієнтів для маркетингових кампаній"""

    # VIP клієнти для персональних пропозицій
    vip_clients = Client.objects.filter(akb_segment='vip')

    # Клієнти з ризиком відтоку для реактивації
    churn_risk = Client.objects.filter(
        temperature='sleeping',
        total_spent__gte=5000
    )

    # Лояльні клієнти для програм лояльності
    loyal_clients = Client.objects.filter(
        temperature='loyal',
        total_orders__gte=3
    )

    # Нові клієнти для онбордингу
    new_customers = Client.objects.filter(
        total_orders=1,
        first_purchase_date__gte=timezone.now() - timedelta(days=30)
    )

    segments_data = {
        'vip_clients': {
            'count': vip_clients.count(),
            'description': 'VIP клієнти для персональних пропозицій',
            'avg_spent': float(vip_clients.aggregate(avg=Avg('total_spent'))['avg'] or 0),
            'clients': [
                {'id': c.id, 'name': c.full_name, 'phone': c.phone, 'total_spent': float(c.total_spent)}
                for c in vip_clients[:5]
            ]
        },
        'churn_risk': {
            'count': churn_risk.count(),
            'description': 'Цінні клієнти з ризиком відтоку',
            'potential_loss': float(churn_risk.aggregate(total=Sum('total_spent'))['total'] or 0),
            'clients': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'days_inactive': c.rfm_recency,
                    'total_spent': float(c.total_spent)
                }
                for c in churn_risk[:5]
            ]
        },
        'loyal_clients': {
            'count': loyal_clients.count(),
            'description': 'Лояльні клієнти для програм лояльності',
            'avg_orders': float(loyal_clients.aggregate(avg=Avg('total_orders'))['avg'] or 0),
            'clients': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'total_orders': c.total_orders
                }
                for c in loyal_clients[:5]
            ]
        },
        'new_customers': {
            'count': new_customers.count(),
            'description': 'Нові клієнти для онбордингу',
            'total_revenue': float(new_customers.aggregate(total=Sum('total_spent'))['total'] or 0),
            'clients': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'first_purchase': c.first_purchase_date
                }
                for c in new_customers[:5]
            ]
        }
    }

    return api_response(
        data={
            "segments": segments_data
        },
        meta={
            "total_segments": len(segments_data),
            "analysis_date": timezone.now(),
            "segments_summary": {
                segment: data['count']
                for segment, data in segments_data.items()
            }
        }
    )


def get_viewset_method(viewset_class, method_name):
    """
    🔧 Допоміжна функція для використання ViewSet методів як окремих view
    Перетворює метод ViewSet в звичайну Django view функцію
    """

    def view_func(request, **kwargs):
        try:
            viewset = viewset_class()
            viewset.request = request
            viewset.format_kwarg = None

            # Додаємо метаінформацію про виклик
            result = getattr(viewset, method_name)(request, **kwargs)

            # Якщо це Response об'єкт - додаємо мета-інформацію
            if hasattr(result, 'data') and isinstance(result.data, dict):
                if 'meta' not in result.data:
                    result.data['meta'] = {}

                result.data['meta'].update({
                    "viewset_method": f"{viewset_class.__name__}.{method_name}",
                    "called_at": timezone.now(),
                    "request_method": request.method
                })

            return result

        except Exception as e:
            return api_response(
                errors={
                    "viewset_error": f"Помилка виклику методу {method_name}",
                    "details": str(e),
                    "viewset_class": viewset_class.__name__
                },
                meta={
                    "error_time": timezone.now(),
                    "attempted_method": method_name
                },
                status_code=500
            )

    # Зберігаємо метаінформацію про оригінальну функцію
    view_func.__name__ = f"{viewset_class.__name__}_{method_name}_view"
    view_func.__doc__ = f"Wrapped ViewSet method: {viewset_class.__name__}.{method_name}"

    return view_func


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lead_statuses(request):
    """📊 Отримання всіх можливих статусів лідів"""

    # Отримуємо всі статуси з моделі Lead
    status_choices = Lead.STATUS_CHOICES

    # Формуємо список статусів
    statuses_data = [
        {
            "code": status_code,
            "name": status_name
        }
        for status_code, status_name in status_choices
    ]

    return api_response(
        data={
            "statuses": statuses_data
        },
        meta={
            "total_statuses": len(status_choices),
            "generated_at": timezone.now()
        }
    )
