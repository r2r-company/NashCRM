
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
from rest_framework.parsers import MultiPartParser, FormParser

# 🚀 УТИЛІТА ДЛЯ РОЗУМНОГО ОЧИЩЕННЯ КЕШУ
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ping(request):
    return Response({"msg": f"Привіт, {request.user.username}!"})


def home(request):
    return render(request, "base.html")


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        raw = response.data

        tokens = {
            "access": raw.get("access"),
            "refresh": raw.get("refresh"),
        }
        user_info = {
            k: v for k, v in raw.items() if k not in tokens
        }

        response.data = {
            "data": {
                **tokens,
                "user": user_info
            },
            "meta": {}
        }
        return response


class LoginView(APIView):
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(username=username, password=password)
        if user is None:
            return Response({"detail": "Невірний логін або пароль"}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)

        try:
            custom_user = CustomUser.objects.select_related('user').get(user=user)
            interface_type = custom_user.interface_type
        except CustomUser.DoesNotExist:
            interface_type = None

        groups = list(user.groups.values_list("name", flat=True))
        permissions = list(user.user_permissions.values_list("codename", flat=True))

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "interface_type": interface_type,
                "groups": groups,
                "permissions": permissions,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "last_login": user.last_login,
                "date_joined": user.date_joined,
            }
        })


class ClientViewSet(viewsets.ModelViewSet):
    # 🔥 ОБОВ'ЯЗКОВО ДОДАЄМО queryset та serializer_class
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

    # ВСІ ВАШІ ІСНУЮЧІ @action МЕТОДИ ЗАЛИШАЮТЬСЯ:

    @action(detail=True, methods=['get'])
    def leads(self, request, pk=None):
        client = self.get_object()
        # 🚀 КОРОТКИЙ КЕШ для даних клієнта (30 секунд)
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
                } for lead in leads
            ]
            cache.set(cache_key, cached_result, 30)  # 30 секунд замість 5 хвилин

        return Response(cached_result)

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        client = self.get_object()

        # 🚀 КОРОТКИЙ КЕШ для платежів (30 секунд)
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
            cache.set(cache_key, cached_result, 30)  # 30 секунд

        return Response(cached_result)

    # 🔥 НОВІ CRM МЕТОДИ:

    @action(detail=False, methods=['get'])
    def temperature_stats(self, request):
        """📊 Статистика по температурі лідів"""
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
                'label': dict(Client.TEMPERATURE_CHOICES).get(temp, temp)
            }

        return Response(result)

    @action(detail=False, methods=['get'])
    def akb_segments(self, request):
        """💰 Статистика по сегментам АКБ"""
        stats = Client.objects.filter(
            akb_segment__in=['vip', 'premium', 'standard', 'basic']
        ).values('akb_segment').annotate(
            count=Count('id'),
            total_revenue=Sum('total_spent'),
            avg_ltv=Avg('total_spent')
        ).order_by('-total_revenue')

        return Response({
            'segments': list(stats),
            'total_akb_clients': sum(s['count'] for s in stats),
            'total_akb_revenue': sum(float(s['total_revenue'] or 0) for s in stats)
        })

    @action(detail=False, methods=['get'])
    def rfm_analysis(self, request):
        """📈 RFM аналіз клієнтів"""
        # Топ клієнти по RFM
        top_clients = Client.objects.filter(
            total_orders__gt=0
        ).order_by('-total_spent')[:10]

        # Розподіл по RFM сегментах
        rfm_distribution = {}
        for client in Client.objects.filter(rfm_score__isnull=False):
            score = client.rfm_score
            if score not in rfm_distribution:
                rfm_distribution[score] = 0
            rfm_distribution[score] += 1

        return Response({
            'top_clients': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'total_spent': float(c.total_spent),
                    'rfm_score': c.rfm_score,
                    'segment': c.akb_segment
                }
                for c in top_clients
            ],
            'rfm_distribution': rfm_distribution
        })

    @action(detail=False, methods=['get'])
    def churn_risk(self, request):
        """⚠️ Клієнти з ризиком відтоку"""
        risky_clients = Client.objects.filter(
            Q(temperature='sleeping') | Q(rfm_recency__gt=180)
        ).filter(total_orders__gt=0).order_by('-total_spent')[:20]

        return Response({
            'risky_clients': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'last_purchase': c.last_purchase_date,
                    'days_since_purchase': c.rfm_recency,
                    'total_spent': float(c.total_spent),
                    'risk_level': c.risk_of_churn,
                    'recommendation': c.next_contact_recommendation
                }
                for c in risky_clients
            ]
        })

    @action(detail=False, methods=['get'])
    def hot_leads(self, request):
        """🔥 Гарячі ліди для менеджерів"""
        hot_clients = Client.objects.filter(
            temperature='hot'
        ).order_by('-created_at')[:20]

        return Response({
            'hot_leads': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'assigned_to': c.assigned_to.username if c.assigned_to else None,
                    'created_at': c.created_at,
                    'leads_count': Lead.objects.filter(phone=c.phone).count(),
                    'recommendation': c.next_contact_recommendation
                }
                for c in hot_clients
            ]
        })

    @action(detail=True, methods=['get'])
    def client_journey(self, request, pk=None):
        """🛤️ Подорож клієнта (Customer Journey)"""
        client = self.get_object()

        # Всі ліди клієнта
        leads = Lead.objects.filter(phone=client.phone).order_by('created_at')

        # Всі взаємодії (якщо модель існує)
        try:
            from backend.models import ClientInteraction
            interactions = ClientInteraction.objects.filter(
                client=client
            ).order_by('created_at')
        except ImportError:
            interactions = []

        # Платежі
        payments = LeadPaymentOperation.objects.filter(
            lead__phone=client.phone
        ).order_by('created_at')

        # Створюємо хронологію
        timeline = []

        for lead in leads:
            timeline.append({
                'type': 'lead',
                'date': lead.created_at,
                'title': f'Створено лід: {lead.full_name}',
                'details': {
                    'status': lead.status,
                    'price': float(lead.price or 0),
                    'source': lead.source
                }
            })

        for interaction in interactions:
            timeline.append({
                'type': 'interaction',
                'date': interaction.created_at,
                'title': f'{interaction.get_interaction_type_display()}: {interaction.subject}',
                'details': {
                    'outcome': interaction.outcome,
                    'description': interaction.description
                }
            })

        for payment in payments:
            timeline.append({
                'type': 'payment',
                'date': payment.created_at,
                'title': f'Платіж: {payment.amount} грн',
                'details': {
                    'type': payment.operation_type,
                    'comment': payment.comment
                }
            })

        # Сортуємо по даті
        timeline.sort(key=lambda x: x['date'])

        return Response({
            'client': {
                'id': client.id,
                'name': client.full_name,
                'phone': client.phone,
                'temperature': getattr(client, 'temperature', 'cold'),
                'akb_segment': getattr(client, 'akb_segment', 'new'),
                'total_spent': float(getattr(client, 'total_spent', 0)),
                'rfm_score': getattr(client, 'rfm_score', '')
            },
            'timeline': timeline,
            'summary': {
                'total_leads': leads.count(),
                'total_interactions': len(interactions),
                'total_payments': payments.count(),
                'customer_since': getattr(client, 'first_purchase_date', None),
                'ltv': float(getattr(client, 'customer_lifetime_value', 0)) if hasattr(client,
                                                                                       'customer_lifetime_value') else 0
            }
        })

    @action(detail=True, methods=['post'])
    def update_temperature(self, request, pk=None):
        """🌡️ Ручне оновлення температури клієнта"""
        client = self.get_object()
        new_temperature = request.data.get('temperature')

        # Перевіряємо чи поле існує
        if not hasattr(client, 'temperature'):
            return Response({
                'error': 'Поле temperature не існує в моделі Client. Потрібно застосувати міграції.'
            }, status=400)

        from backend.models import Client
        if new_temperature not in dict(Client.TEMPERATURE_CHOICES):
            return Response({
                'error': 'Неправильна температура'
            }, status=400)

        old_temperature = client.temperature
        client.temperature = new_temperature
        client.save()

        return Response({
            'message': f'Температура змінена: {old_temperature} → {new_temperature}',
            'client_id': client.id,
            'old_temperature': old_temperature,
            'new_temperature': new_temperature
        })

    @action(detail=False, methods=['get'])
    def akb_segments(self, request):
        """💰 Статистика по сегментам АКБ"""
        stats = Client.objects.filter(
            akb_segment__in=['vip', 'premium', 'standard', 'basic']
        ).values('akb_segment').annotate(
            count=Count('id'),
            total_revenue=Sum('total_spent'),
            avg_ltv=Avg('total_spent')
        ).order_by('-total_revenue')

        return Response({
            'segments': list(stats),
            'total_akb_clients': sum(s['count'] for s in stats),
            'total_akb_revenue': sum(float(s['total_revenue'] or 0) for s in stats)
        })

    @action(detail=False, methods=['get'])
    def rfm_analysis(self, request):
        """📈 RFM аналіз клієнтів"""
        # Топ клієнти по RFM
        top_clients = Client.objects.filter(
            total_orders__gt=0
        ).order_by('-total_spent')[:10]

        # Розподіл по RFM сегментах
        rfm_distribution = {}
        for client in Client.objects.filter(rfm_score__isnull=False):
            score = client.rfm_score
            if score not in rfm_distribution:
                rfm_distribution[score] = 0
            rfm_distribution[score] += 1

        return Response({
            'top_clients': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'total_spent': float(c.total_spent),
                    'rfm_score': c.rfm_score,
                    'segment': c.akb_segment
                }
                for c in top_clients
            ],
            'rfm_distribution': rfm_distribution
        })

    @action(detail=False, methods=['get'])
    def churn_risk(self, request):
        """⚠️ Клієнти з ризиком відтоку"""
        risky_clients = Client.objects.filter(
            Q(temperature='sleeping') | Q(rfm_recency__gt=180)
        ).filter(total_orders__gt=0).order_by('-total_spent')[:20]

        return Response({
            'risky_clients': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'last_purchase': c.last_purchase_date,
                    'days_since_purchase': c.rfm_recency,
                    'total_spent': float(c.total_spent),
                    'risk_level': c.risk_of_churn,
                    'recommendation': c.next_contact_recommendation
                }
                for c in risky_clients
            ]
        })

    @action(detail=False, methods=['get'])
    def hot_leads(self, request):
        """🔥 Гарячі ліди для менеджерів"""
        hot_clients = Client.objects.filter(
            temperature='hot'
        ).order_by('-created_at')[:20]

        return Response({
            'hot_leads': [
                {
                    'id': c.id,
                    'name': c.full_name,
                    'phone': c.phone,
                    'assigned_to': c.assigned_to.username if c.assigned_to else None,
                    'created_at': c.created_at,
                    'leads_count': Lead.objects.filter(phone=c.phone).count(),
                    'recommendation': c.next_contact_recommendation
                }
                for c in hot_clients
            ]
        })

    @action(detail=True, methods=['get'])
    def client_journey(self, request, pk=None):
        """🛤️ Подорож клієнта (Customer Journey)"""
        client = self.get_object()

        # Всі ліди клієнта
        leads = Lead.objects.filter(phone=client.phone).order_by('created_at')

        # Всі взаємодії
        interactions = ClientInteraction.objects.filter(
            client=client
        ).order_by('created_at')

        # Платежі
        payments = LeadPaymentOperation.objects.filter(
            lead__phone=client.phone
        ).order_by('created_at')

        # Створюємо хронологію
        timeline = []

        for lead in leads:
            timeline.append({
                'type': 'lead',
                'date': lead.created_at,
                'title': f'Створено лід: {lead.full_name}',
                'details': {
                    'status': lead.status,
                    'price': float(lead.price or 0),
                    'source': lead.source
                }
            })

        for interaction in interactions:
            timeline.append({
                'type': 'interaction',
                'date': interaction.created_at,
                'title': f'{interaction.get_interaction_type_display()}: {interaction.subject}',
                'details': {
                    'outcome': interaction.outcome,
                    'description': interaction.description
                }
            })

        for payment in payments:
            timeline.append({
                'type': 'payment',
                'date': payment.created_at,
                'title': f'Платіж: {payment.amount} грн',
                'details': {
                    'type': payment.operation_type,
                    'comment': payment.comment
                }
            })

        # Сортуємо по даті
        timeline.sort(key=lambda x: x['date'])

        return Response({
            'client': {
                'id': client.id,
                'name': client.full_name,
                'phone': client.phone,
                'temperature': client.temperature,
                'akb_segment': client.akb_segment,
                'total_spent': float(client.total_spent),
                'rfm_score': client.rfm_score
            },
            'timeline': timeline,
            'summary': {
                'total_leads': leads.count(),
                'total_interactions': interactions.count(),
                'total_payments': payments.count(),
                'customer_since': client.first_purchase_date,
                'ltv': float(client.customer_lifetime_value)
            }
        })

    @action(detail=True, methods=['post'])
    def update_temperature(self, request, pk=None):
        """🌡️ Ручне оновлення температури клієнта"""
        client = self.get_object()
        new_temperature = request.data.get('temperature')

        if new_temperature not in dict(Client.TEMPERATURE_CHOICES):
            return Response({
                'error': 'Неправильна температура'
            }, status=400)

        old_temperature = client.temperature
        client.temperature = new_temperature
        client.save()

        return Response({
            'message': f'Температура змінена: {old_temperature} → {new_temperature}',
            'client_id': client.id,
            'old_temperature': old_temperature,
            'new_temperature': new_temperature
        })


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


# 🚀 ОНОВІТЬ ExternalLeadView
class ExternalLeadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        print(f"📥 API: Отримано запит на створення ліда: {request.data}")

        serializer = ExternalLeadSerializer(data=request.data)
        if serializer.is_valid():
            # 🛡️ ПЕРЕВІРКА НА ДУБЛІКАТ ПЕРЕД СТВОРЕННЯМ
            phone = serializer.validated_data.get('phone')
            full_name = serializer.validated_data.get('full_name')
            order_number = serializer.validated_data.get('order_number')  # Якщо є

            is_duplicate, existing_lead = check_duplicate_lead(
                phone=phone,
                full_name=full_name,
                order_number=order_number,
                time_window_minutes=30  # Перевіряємо за останні 30 хвилин
            )

            if is_duplicate:
                print(f"🚫 ДУБЛІКАТ! Знайдено існуючий лід #{existing_lead.id}")
                return Response({
                    "error": "DUPLICATE_LEAD",
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
                }, status=status.HTTP_409_CONFLICT)  # 409 = Conflict

            # Якщо не дублікат - створюємо лід
            print(f"✅ Не дублікат - створюємо новий лід")
            lead, context = create_lead_with_logic(serializer.validated_data)

            # Очищуємо кеш
            smart_cache_invalidation(
                lead_id=lead.id,
                manager_id=lead.assigned_to.id if lead.assigned_to else None
            )

            return Response({
                "success": True,
                "lead_id": lead.id,
                "client_name": lead.full_name,
                "assigned_manager": context['assigned_to'],
                "status": context['final_status'],
                "created_at": lead.created_at,
                "details": context,
                "message": f"✅ Лід створено для {lead.full_name} — статус: {context['final_status'].upper()}"
            }, status=status.HTTP_201_CREATED)

        return Response({
            "error": "VALIDATION_ERROR",
            "details": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def leads_report(request):
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if not date_from or not date_to:
        return Response({"error": "Потрібно вказати ?date_from=...&date_to=..."}, status=400)

    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return Response({"error": "Невірний формат дати. Використовуйте YYYY-MM-DD"}, status=400)

    # 🚀 СКОРОЧУЄМО КЕШ до 60 секунд для звітів
    cache_key = f"leads_report_{date_from}_{date_to}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

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
        "total": leads.count(),
        "by_status": status_counts,
        "expected_sum": expected_sum,
        "received_sum": received_sum,
        "delta": delta
    }

    # 🚀 СКОРОЧУЄМО КЕШ до 60 секунд
    cache.set(cache_key, result, 60)
    return Response(result)


@staff_member_required
def leads_report_page(request):
    form = LeadsReportForm(request.GET or None)
    context = {"form": form}

    if form.is_valid():
        pass

    return render(request, "admin/reports/leads_report_form.html", context)


User = get_user_model()


class LeadsReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from = parse_date(request.GET.get('date_from'))
        date_to = parse_date(request.GET.get('date_to'))

        # 🚀 СКОРОЧУЄМО КЕШ до 2 хвилин для детального звіту
        cache_key = f"detailed_report_{date_from}_{date_to}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return Response(cached_result)

        leads = Lead.objects.select_related('assigned_to')
        if date_from:
            leads = leads.filter(created_at__date__gte=date_from)
        if date_to:
            leads = leads.filter(created_at__date__lte=date_to)

        now_date = now()

        # Звіт по менеджерах
        managers_stats = leads.values(
            'assigned_to__id',
            'assigned_to__username'
        ).annotate(
            total_leads=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            in_work=Count('id', filter=Q(status='in_work')),
            queued=Count('id', filter=Q(status='queued')),
            total_price=Sum('price', filter=Q(status='completed')),
            avg_check=Avg('price', filter=Q(status='completed'))
        ).filter(assigned_to__isnull=False)

        managers_report = []
        for stat in managers_stats:
            conversion = round((stat['completed'] / stat['total_leads']) * 100, 1) if stat['total_leads'] else 0
            avg_check = round(float(stat['avg_check'] or 0), 2)

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
                "manager": stat['assigned_to__username'],
                "total_leads": stat['total_leads'],
                "completed": stat['completed'],
                "in_work": stat['in_work'],
                "queued": stat['queued'],
                "total_price": str(float(stat['total_price'] or 0)),
                "avg_duration_minutes": avg_minutes,
                "conversion_rate": f"{conversion}%",
                "avg_check": f"{avg_check}",
            })

        # Борги по клієнтах
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

        clients_report = [
            {
                "client": debt['full_name'],
                "phone": debt['phone'],
                "total_unpaid": str(float(debt['debt'] or 0)),
                "received": str(float(debt['total_received'] or 0)),
                "expected": str(float(debt['total_price'] or 0))
            }
            for debt in client_debts
        ]

        top_debts = sorted(clients_report, key=lambda x: float(x['total_unpaid']), reverse=True)[:5]

        # Воронка
        funnel_data = leads.aggregate(
            queued=Count('id', filter=Q(status='queued')),
            in_work=Count('id', filter=Q(status='in_work')),
            awaiting_prepayment=Count('id', filter=Q(status='awaiting_prepayment')),
            preparation=Count('id', filter=Q(status='preparation')),
            warehouse_processing=Count('id', filter=Q(status='warehouse_processing')),
            on_the_way=Count('id', filter=Q(status='on_the_way')),
            completed=Count('id', filter=Q(status='completed')),
            declined=Count('id', filter=Q(status='declined'))
        )

        # Статистика за день
        daily_stats = Lead.objects.aggregate(
            new_today=Count('id', filter=Q(created_at__date=now_date.date())),
            completed_today=Count('id', filter=Q(
                status='completed',
                status_updated_at__date=now_date.date()
            )),
            last_7_days=Count('id', filter=Q(
                created_at__gte=now_date - timedelta(days=7)
            ))
        )

        # Проблемні ліди
        long_in_work_ids = list(Lead.objects.filter(
            status="in_work",
            created_at__lte=now_date - timedelta(days=1)
        ).values_list("id", flat=True))

        paid_lead_ids = set(LeadPaymentOperation.objects.filter(
            operation_type='received'
        ).values_list('lead_id', flat=True))

        without_cash_ids = list(leads.filter(
            status="completed"
        ).exclude(id__in=paid_lead_ids).values_list("id", flat=True))

        result = {
            "managers": managers_report,
            "debts": clients_report,
            "top_debtors": top_debts,
            "funnel": funnel_data,
            "stats": daily_stats,
            "delayed_leads": long_in_work_ids,
            "completed_without_cash": without_cash_ids,
        }

        # 🚀 СКОРОЧУЄМО КЕШ до 2 хвилин
        cache.set(cache_key, result, 120)
        return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geocode_address(request):
    address = request.query_params.get("address")
    if not address:
        return Response({"error": "Потрібно передати параметр ?address="}, status=400)

    # Геокодування можна кешувати довго
    cache_key = f"geocode_{hash(address)}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": settings.GOOGLE_MAPS_API_KEY
    }

    response = requests.get(url, params=params).json()
    if response["status"] != "OK":
        return Response({"error": "Нічого не знайдено або помилка Google"}, status=400)

    result_data = response["results"][0]
    location = result_data["geometry"]["location"]
    components = {c['types'][0]: c['long_name'] for c in result_data['address_components']}

    result = {
        "address": result_data["formatted_address"],
        "lat": location["lat"],
        "lng": location["lng"],
        "country": components.get("country"),
        "city": components.get("locality") or components.get("administrative_area_level_1"),
        "postal_code": components.get("postal_code"),
        "street": components.get("route"),
    }

    cache.set(cache_key, result, 86400)  # Адреси можна кешувати на день
    return Response(result)


@staff_member_required
def map_search_view(request):
    return render(request, "admin/map_search.html", {
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def funnel_data(request):
    date_from_raw = request.GET.get("from")
    date_to_raw = request.GET.get("to")
    manager_id = request.GET.get("manager_id")

    # 🚀 СКОРОЧУЄМО КЕШ воронки до 30 секунд!
    cache_key = f"funnel_{date_from_raw}_{date_to_raw}_{manager_id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None

    leads = Lead.objects.all()

    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)
    if manager_id:
        leads = leads.filter(assigned_to_id=manager_id)

    funnel = leads.aggregate(
        queued=Count('id', filter=Q(status='queued')),
        in_work=Count('id', filter=Q(status='in_work')),
        awaiting_prepayment=Count('id', filter=Q(status='awaiting_prepayment')),
        preparation=Count('id', filter=Q(status='preparation')),
        warehouse_processing=Count('id', filter=Q(status='warehouse_processing')),
        on_the_way=Count('id', filter=Q(status='on_the_way')),
        completed=Count('id', filter=Q(status='completed')),
        declined=Count('id', filter=Q(status='declined'))
    )

    total_attempted = sum(funnel.values())
    conversion = round((funnel["completed"] / total_attempted) * 100, 1) if total_attempted > 0 else 0.0

    result = {
        "funnel": funnel,
        "conversion_rate": f"{conversion}%"
    }

    # 🚀 КЕШ воронки тільки 30 секунд!
    cache.set(cache_key, result, 30)
    return Response(result)


# Замініть ваш LeadViewSet на цю версію з перевіркою дублікатів:

class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.select_related('assigned_to').prefetch_related(
        Prefetch('payment_operations', queryset=LeadPaymentOperation.objects.order_by('-created_at'))
    ).order_by('-created_at')
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 🚀 УБИРАЄМО КЕШ для списку лідів - завжди актуальні дані
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        """
        🛡️ ПЕРЕВАИЗНАЧЕНИЙ CREATE З ПЕРЕВІРКОЮ ДУБЛІКАТІВ
        """
        print(f"📥 LeadViewSet CREATE: Отримано запит: {request.data}")

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # 🛡️ ПЕРЕВІРКА НА ДУБЛІКАТ ПЕРЕД СТВОРЕННЯМ
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
                print(f"🚫 LeadViewSet ДУБЛІКАТ! Знайдено лід #{existing_lead.id}")
                return Response({
                    "error": "DUPLICATE_LEAD",
                    "message": f"Лід з таким номером телефону вже створено {existing_lead.created_at.strftime('%H:%M:%S')}",
                    "existing_lead": {
                        "id": existing_lead.id,
                        "full_name": existing_lead.full_name,
                        "phone": existing_lead.phone,
                        "created_at": existing_lead.created_at,
                        "status": existing_lead.status,
                        "minutes_ago": int((timezone.now() - existing_lead.created_at).total_seconds() / 60)
                    },
                    "duplicate_details": {
                        "normalized_phone": Client.normalize_phone(phone) if phone else None,
                        "time_window_checked": "30 minutes",
                        "match_type": "phone + name" if full_name else "phone only"
                    }
                }, status=status.HTTP_409_CONFLICT)

            # Якщо не дублікат - створюємо
            print(f"✅ LeadViewSet: Створюємо новий лід")
            self.perform_create(serializer)

            # Очищуємо кеш
            smart_cache_invalidation(
                lead_id=serializer.instance.id,
                manager_id=serializer.instance.assigned_to.id if serializer.instance.assigned_to else None
            )

            headers = self.get_success_headers(serializer.data)
            return Response({
                "success": True,
                "message": "✅ Лід успішно створено",
                "lead": serializer.data
            }, status=status.HTTP_201_CREATED, headers=headers)

        return Response({
            "error": "VALIDATION_ERROR",
            "details": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    # Решта методів залишаються без змін...
    @action(detail=True, methods=['post'])
    def upload_file(self, request, pk=None):
        lead = self.get_object()
        files = request.FILES.getlist('file')
        if not files:
            return Response({"error": "Файли не передано"}, status=400)

        result = []
        for f in files:
            obj = LeadFile.objects.create(lead=lead, file=f)
            result.append({
                "file_id": obj.id,
                "file_name": obj.file.name,
            })

        return Response({
            "message": f"✅ Додано {len(result)} файл(и)",
            "files": result
        })

    @action(detail=True, methods=['get'])
    def files(self, request, pk=None):
        lead = self.get_object()
        files = lead.uploaded_files.all()

        result = [{
            "id": f.id,
            "name": f.file.name,
            "url": request.build_absolute_uri(f.file.url),
            "uploaded_at": f.uploaded_at,
        } for f in files]

        return Response({
            "lead_id": lead.id,
            "files": result
        })

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        lead = self.get_object()

        # 🚀 СКОРОЧУЄМО КЕШ платежів до 30 секунд
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
            cache.set(cache_key, cached_payments, 30)  # 30 секунд

        return Response(cached_payments)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        lead = self.get_object()

        operation_type = request.data.get('operation_type')
        amount = request.data.get('amount')
        comment = request.data.get('comment', '')

        if not operation_type or not amount:
            return Response({"error": "operation_type і amount обов'язкові"}, status=400)

        payment = LeadPaymentOperation.objects.create(
            lead=lead,
            operation_type=operation_type,
            amount=amount,
            comment=comment
        )

        # 🚀 РОЗУМНЕ ОЧИЩЕННЯ КЕШУ
        smart_cache_invalidation(
            lead_id=lead.id,
            manager_id=lead.assigned_to.id if lead.assigned_to else None
        )

        return Response({
            "message": "✅ Платіж додано",
            "payment": {
                "id": payment.id,
                "type": payment.operation_type,
                "amount": float(payment.amount),
                "comment": payment.comment,
                "created_at": payment.created_at,
            }
        }, status=201)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        lead = self.get_object()
        new_status = request.data.get('status')
        old_status = lead.status

        if not new_status:
            return Response({"error": "Потрібно вказати статус"}, status=400)

        allowed_transitions = {
            'queued': ['in_work', 'declined'],
            'in_work': ['awaiting_packaging', 'declined'],
            'awaiting_packaging': ['on_the_way', 'declined'],
            'on_the_way': ['awaiting_cash', 'completed', 'declined'],
            'awaiting_cash': ['completed'],
            'completed': [],
            'declined': [],
        }

        if new_status not in allowed_transitions.get(old_status, []):
            return Response({
                "error": f"Не можна перейти зі статусу '{old_status}' у '{new_status}'"
            }, status=422)

        if new_status == 'preparation':
            if not lead.price or lead.price <= 0:
                return Response({"error": "Ціна повинна бути вказана перед підготовкою!"}, status=400)

        try:
            lead.status = new_status
            lead.save()

            # 🚀 РОЗУМНЕ ОЧИЩЕННЯ КЕШУ - ТУТ ГОЛОВНЕ!
            smart_cache_invalidation(
                lead_id=lead.id,
                manager_id=lead.assigned_to.id if lead.assigned_to else None
            )

            if new_status == "on_the_way":
                LeadPaymentOperation.objects.get_or_create(
                    lead=lead,
                    operation_type='expected',
                    defaults={
                        "amount": lead.price,
                        "comment": f"Очікується оплата за лід #{lead.id}"
                    }
                )

            elif new_status == "completed":
                LeadPaymentOperation.objects.create(
                    lead=lead,
                    operation_type='received',
                    amount=lead.actual_cash or lead.price,
                    comment=f"Отримано по завершенню ліда #{lead.id}"
                )
                if lead.assigned_to:
                    from backend.services.lead_queue import on_lead_closed
                    on_lead_closed(lead)

            elif new_status == "declined":
                if lead.assigned_to:
                    from backend.services.lead_queue import on_lead_closed
                    on_lead_closed(lead)

            return Response({
                "message": f"✅ Статус змінено на {new_status}",
                "lead_id": lead.id,
                "new_status": new_status
            })
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    @action(detail=True, methods=['get'])
    def available_statuses(self, request, pk=None):
        lead = self.get_object()
        current_status = lead.status

        allowed_transitions = {
            'queued': ['in_work', 'declined'],
            'in_work': ['awaiting_packaging', 'declined'],
            'awaiting_packaging': ['on_the_way', 'declined'],
            'on_the_way': ['awaiting_cash', 'completed', 'declined'],
            'awaiting_cash': ['completed'],
            'completed': [],
            'declined': [],
        }

        status_descriptions = {
            'queued': 'У черзі',
            'in_work': 'Обробляється менеджером',
            'awaiting_prepayment': 'Очікую аванс',
            'preparation': 'В роботу',
            'warehouse_processing': 'Склад',
            'on_the_way': 'В дорозі',
            'completed': 'Завершено',
            'declined': 'Відмовлено'
        }

        available = allowed_transitions.get(current_status, [])

        return Response({
            'lead_id': lead.id,
            'lead_name': lead.full_name,
            'current_status': {
                'code': current_status,
                'description': status_descriptions.get(current_status, current_status)
            },
            'available_statuses': [
                {
                    'code': status_code,
                    'description': status_descriptions.get(status_code, status_code),
                    'requires_additional_data': False
                }
                for status_code in available
            ],
            'is_final': len(available) == 0,
            'workflow_position': self._get_workflow_position(current_status)
        })

    def _get_workflow_position(self, status):
        workflow = [
            'queued',
            'in_work',
            'awaiting_prepayment',
            'preparation',
            'warehouse_processing',
            'on_the_way',
            'completed'
        ]

        try:
            position = workflow.index(status) + 1
            return {
                'step': position,
                'total_steps': len(workflow),
                'progress_percent': round((position / len(workflow)) * 100, 1)
            }
        except ValueError:
            return {'step': 'unknown', 'total_steps': len(workflow), 'progress_percent': 0}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def all_payments(request):
    lead_id = request.GET.get("lead_id")
    client_id = request.GET.get("client_id")
    op_type = request.GET.get("type")

    # 🚀 СКОРОЧУЄМО КЕШ платежів до 60 секунд
    cache_key = f"payments_{lead_id}_{client_id}_{op_type}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

    payments = LeadPaymentOperation.objects.select_related('lead')

    if lead_id:
        payments = payments.filter(lead_id=lead_id)
    if client_id:
        payments = payments.filter(lead__phone__in=
                                   Client.objects.filter(id=client_id).values_list("phone", flat=True)
                                   )
    if op_type:
        payments = payments.filter(operation_type=op_type)

    result = [
        {
            "id": p.id,
            "lead_id": p.lead_id,
            "type": p.operation_type,
            "amount": float(p.amount),
            "comment": p.comment,
            "created_at": p.created_at,
        } for p in payments.order_by("-created_at")
    ]

    # 🚀 СКОРОЧУЄМО до 60 секунд
    cache.set(cache_key, result, 60)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_managers(request):
    # 🚀 СКОРОЧУЄМО КЕШ менеджерів до 2 хвилин
    cache_key = "managers_list"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

    managers = CustomUser.objects.select_related('user').filter(interface_type='accountant')
    serializer = ManagerSerializer(managers, many=True)

    # 🚀 СКОРОЧУЄМО до 2 хвилин
    cache.set(cache_key, serializer.data, 120)
    return Response(serializer.data)


class ManagerViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.select_related('user').filter(interface_type='accountant')
    serializer_class = ManagerSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # 🚀 РОЗУМНЕ ОЧИЩЕННЯ КЕШУ
        smart_cache_invalidation()
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        # 🚀 РОЗУМНЕ ОЧИЩЕННЯ КЕШУ
        smart_cache_invalidation()
        return response

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        # 🚀 РОЗУМНЕ ОЧИЩЕННЯ КЕШУ
        smart_cache_invalidation()
        return response


class CreateLeadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        print(f"📥 CREATE API: Отримано запит: {request.data}")

        serializer = LeadSerializer(data=request.data)
        if serializer.is_valid():
            order_number = serializer.validated_data.get('order_number')

            # 🛡️ ПЕРЕВІРКА ПО НОМЕРУ ЗАМОВЛЕННЯ
            if order_number:
                existing = Lead.objects.filter(order_number=order_number).first()
                if existing:
                    print(f"🚫 ДУБЛІКАТ! Номер замовлення {order_number} вже є в ліді #{existing.id}")
                    return Response({
                        "error": f"Номер замовлення {order_number} вже використовується!",
                        "existing_lead": {
                            "id": existing.id,
                            "full_name": existing.full_name,
                            "phone": existing.phone,
                            "created_at": existing.created_at
                        }
                    }, status=409)

            # Створюємо лід
            lead = serializer.save()
            print(f"✅ Створено лід #{lead.id} з номером замовлення {order_number}")

            return Response({
                "success": True,
                "lead_id": lead.id,
                "order_number": order_number,
                "message": f"Лід створено з номером замовлення {order_number}"
            }, status=201)

        return Response(serializer.errors, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_lead_duplicate(request):
    """
    Endpoint для перевірки чи є лід дублікатом БЕЗ створення
    """
    phone = request.data.get('phone')
    full_name = request.data.get('full_name')
    order_number = request.data.get('order_number')

    if not phone:
        return Response({"error": "Телефон обов'язковий"}, status=400)

    is_duplicate, existing_lead = check_duplicate_lead(phone, full_name, order_number)

    return Response({
        "is_duplicate": is_duplicate,
        "phone": phone,
        "normalized_phone": Client.normalize_phone(phone),
        "existing_lead": {
            "id": existing_lead.id,
            "full_name": existing_lead.full_name,
            "created_at": existing_lead.created_at,
            "status": existing_lead.status
        } if existing_lead else None
    })


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

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

        # Оновлюємо дату останнього контакту з клієнтом
        client = serializer.instance.client
        client.last_contact_date = timezone.now()
        client.save()


class ClientTaskViewSet(viewsets.ModelViewSet):
    serializer_class = ClientTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ClientTask.objects.select_related(
            'client', 'assigned_to'
        ).order_by('due_date')

        # Фільтри
        client_id = self.request.query_params.get('client_id')
        status = self.request.query_params.get('status')
        assigned_to_me = self.request.query_params.get('assigned_to_me')

        if client_id:
            queryset = queryset.filter(client_id=client_id)
        if status:
            queryset = queryset.filter(status=status)
        if assigned_to_me == 'true':
            queryset = queryset.filter(assigned_to=self.request.user)

        return queryset

    @action(detail=False, methods=['get'])
    def my_tasks(self, request):
        """📋 Мої задачі"""
        tasks = ClientTask.objects.filter(
            assigned_to=request.user,
            status__in=['pending', 'in_progress']
        ).order_by('due_date')[:10]

        return Response({
            'my_tasks': [
                {
                    'id': task.id,
                    'title': task.title,
                    'client_name': task.client.full_name,
                    'client_phone': task.client.phone,
                    'priority': task.priority,
                    'due_date': task.due_date,
                    'overdue': task.due_date < timezone.now()
                }
                for task in tasks
            ]
        })

    @action(detail=False, methods=['get'])
    def overdue_tasks(self, request):
        """⏰ Прострочені задачі"""
        overdue = ClientTask.objects.filter(
            due_date__lt=timezone.now(),
            status__in=['pending', 'in_progress']
        ).order_by('due_date')

        return Response({
            'overdue_tasks': [
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
        })


# 🔥 НОВИЙ API ДЛЯ CRM ДАШБОРДУ
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def crm_dashboard(request):
    """🎯 Головний CRM дашборд"""

    # Кешування дашборду на 5 хвилин
    cache_key = f"crm_dashboard_{request.user.id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

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

    cache.set(cache_key, result, 300)  # 5 хвилин
    return Response(result)


# 🔥 МАСОВЕ ОНОВЛЕННЯ МЕТРИК КЛІЄНТІВ
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_all_client_metrics(request):
    """🔄 Масове оновлення метрик всіх клієнтів"""
    if not request.user.is_staff:
        return Response({
            'error': 'Тільки адміністратори можуть запускати масове оновлення'
        }, status=403)

    updated_count = 0
    errors = []

    for client in Client.objects.all():
        try:
            client.update_client_metrics()
            updated_count += 1
        except Exception as e:
            errors.append(f"Клієнт {client.id}: {str(e)}")

    return Response({
        'message': f'Оновлено метрики для {updated_count} клієнтів',
        'updated_count': updated_count,
        'errors': errors[:10]  # Показуємо перші 10 помилок
    })


# 🔥 АВТОМАТИЧНЕ СТВОРЕННЯ ЗАДАЧ ПО КЛІЄНТАХ
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_follow_up_tasks(request):
    """📅 Автоматичне створення задач для follow-up"""

    # Клієнти що потребують реактивації (сплячі)
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
        created_tasks.append(task)

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
        created_tasks.append(task)

    return Response({
        'message': f'Створено {len(created_tasks)} нових задач',
        'sleeping_clients_tasks': len(sleeping_clients),
        'hot_leads_tasks': len(hot_leads),
        'tasks': [
            {
                'id': task.id,
                'title': task.title,
                'client': task.client.full_name,
                'priority': task.priority,
                'due_date': task.due_date
            }
            for task in created_tasks
        ]
    })


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
        total_spent__gte=5000  # Тільки цінні клієнти
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

    return Response({
        'segments': {
            'vip_clients': {
                'count': vip_clients.count(),
                'description': 'VIP клієнти для персональних пропозицій',
                'avg_spent': vip_clients.aggregate(avg=Avg('total_spent'))['avg'] or 0,
                'clients': [{'id': c.id, 'name': c.full_name, 'phone': c.phone} for c in vip_clients[:5]]
            },
            'churn_risk': {
                'count': churn_risk.count(),
                'description': 'Цінні клієнти з ризиком відтоку',
                'potential_loss': float(churn_risk.aggregate(total=Sum('total_spent'))['total'] or 0),
                'clients': [{'id': c.id, 'name': c.full_name, 'phone': c.phone, 'days_inactive': c.rfm_recency} for c in
                            churn_risk[:5]]
            },
            'loyal_clients': {
                'count': loyal_clients.count(),
                'description': 'Лояльні клієнти для програм лояльності',
                'avg_orders': loyal_clients.aggregate(avg=Avg('total_orders'))['avg'] or 0,
                'clients': [{'id': c.id, 'name': c.full_name, 'phone': c.phone} for c in loyal_clients[:5]]
            },
            'new_customers': {
                'count': new_customers.count(),
                'description': 'Нові клієнти для онбордингу',
                'total_revenue': float(new_customers.aggregate(total=Sum('total_spent'))['total'] or 0),
                'clients': [{'id': c.id, 'name': c.full_name, 'phone': c.phone} for c in new_customers[:5]]
            }
        }
    })
