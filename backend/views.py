from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.db.models import Count, Sum, DurationField, ExpressionWrapper, F, Q, Avg, Case, When, DecimalField, Prefetch
from django.shortcuts import render
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
from datetime import datetime, timedelta

from NashCRM import settings
from backend.forms import LeadsReportForm
from backend.models import CustomUser, Lead, Client, LeadPaymentOperation, LeadFile
from backend.serializers import LeadSerializer, ClientSerializer, ExternalLeadSerializer, MyTokenObtainPairSerializer, \
    ManagerSerializer
from backend.services.lead_creation_service import create_lead_with_logic
from rest_framework.parsers import MultiPartParser, FormParser


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

        # Відділяємо токени і решту
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

        # 🚀 ОПТИМІЗАЦІЯ: Одним запитом отримуємо все
        try:
            custom_user = CustomUser.objects.select_related('user').get(user=user)
            interface_type = custom_user.interface_type
        except CustomUser.DoesNotExist:
            interface_type = None

        # 🚀 ОПТИМІЗАЦІЯ: Ефективне отримання груп і прав
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
    # 🚀 МАКСИМАЛЬНА ОПТИМІЗАЦІЯ: Client з менеджером
    queryset = Client.objects.select_related('assigned_to').order_by('-created_at')
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['get'])
    def leads(self, request, pk=None):
        client = self.get_object()
        # 🚀 ОПТИМІЗАЦІЯ: Завантажуємо менеджера одразу
        leads = Lead.objects.select_related('assigned_to').filter(phone=client.phone)

        return Response([
            {
                "id": lead.id,
                "full_name": lead.full_name,
                "status": lead.status,
                "price": float(lead.price or 0),
                "created_at": lead.created_at,
            } for lead in leads
        ])

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        client = self.get_object()

        # 🚀 ОПТИМІЗАЦІЯ: Одним запитом отримуємо всі платежі
        payments = LeadPaymentOperation.objects.select_related('lead').filter(
            lead__phone=client.phone
        ).order_by('-created_at')

        return Response([
            {
                "id": p.id,
                "lead_id": p.lead_id,
                "type": p.operation_type,
                "amount": float(p.amount),
                "comment": p.comment,
                "created_at": p.created_at,
            } for p in payments
        ])


class ExternalLeadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ExternalLeadSerializer(data=request.data)
        if serializer.is_valid():
            lead, context = create_lead_with_logic(serializer.validated_data)

            return Response({
                "lead_id": lead.id,
                "client_name": lead.full_name,
                "assigned_manager": context['assigned_to'],
                "status": context['final_status'],
                "created_at": lead.created_at,
                "details": context,
                "message": f"Лід створено для {lead.full_name} — статус: {context['final_status'].upper()}"
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

    # 🚀 ОПТИМІЗАЦІЯ: Кешування з унікальним ключем
    cache_key = f"leads_report_{date_from}_{date_to}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

    leads = Lead.objects.filter(created_at__range=(start, end))

    # 🚀 ОПТИМІЗАЦІЯ: Агрегація замість окремих запитів
    status_counts = dict(leads.values('status').annotate(count=Count('id')).values_list('status', 'count'))

    # 🚀 ОПТИМІЗАЦІЯ: Одним запитом отримуємо фінанси
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

    # Кешуємо на 5 хвилин
    cache.set(cache_key, result, 300)
    return Response(result)


@staff_member_required
def leads_report_page(request):
    form = LeadsReportForm(request.GET or None)
    context = {"form": form}

    if form.is_valid():
        # тут можеш формувати аналітику, графіки, whatever
        pass

    return render(request, "admin/reports/leads_report_form.html", context)


User = get_user_model()


class LeadsReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from = parse_date(request.GET.get('date_from'))
        date_to = parse_date(request.GET.get('date_to'))

        # 🚀 ОПТИМІЗАЦІЯ: Кешування складного звіту
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

        # 🚀 ОПТИМІЗАЦІЯ: Звіт по менеджерах одним запитом
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

            # 🚀 ОПТИМІЗАЦІЯ: Розрахунок тривалості окремим запитом тільки для completed
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

        # 🚀 ОПТИМІЗАЦІЯ: Борги по клієнтах одним запитом
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

        # Топ-5 боржників
        top_debts = sorted(clients_report, key=lambda x: float(x['total_unpaid']), reverse=True)[:5]

        # 🚀 ОПТИМІЗАЦІЯ: Воронка одним запитом
        funnel_data = leads.aggregate(
            new=Count('id', filter=Q(status='new')),
            queued=Count('id', filter=Q(status='queued')),
            in_work=Count('id', filter=Q(status='in_work')),
            awaiting_packaging=Count('id', filter=Q(status='awaiting_packaging')),
            on_the_way=Count('id', filter=Q(status='on_the_way')),
            awaiting_cash=Count('id', filter=Q(status='awaiting_cash')),
            completed=Count('id', filter=Q(status='completed'))
        )

        # 🚀 ОПТИМІЗАЦІЯ: Статистика за день одним запитом
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

        # 🚀 ОПТИМІЗАЦІЯ: Проблемні ліди одним запитом
        long_in_work_ids = list(Lead.objects.filter(
            status="in_work",
            created_at__lte=now_date - timedelta(days=1)
        ).values_list("id", flat=True))

        # Ліди без оплат
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

        # Кешуємо на 10 хвилин
        cache.set(cache_key, result, 600)
        return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geocode_address(request):
    address = request.query_params.get("address")
    if not address:
        return Response({"error": "Потрібно передати параметр ?address="}, status=400)

    # 🚀 ОПТИМІЗАЦІЯ: Кешування геокодування
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

    # Кешуємо адреси на 1 день
    cache.set(cache_key, result, 86400)
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

    # 🚀 ОПТИМІЗАЦІЯ: Кешування воронки
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

    # 🚀 ОПТИМІЗАЦІЯ: Одним запитом рахуємо всі статуси
    funnel = leads.aggregate(
        new=Count('id', filter=Q(status='new')),
        queued=Count('id', filter=Q(status='queued')),
        in_work=Count('id', filter=Q(status='in_work')),
        awaiting_packaging=Count('id', filter=Q(status='awaiting_packaging')),
        on_the_way=Count('id', filter=Q(status='on_the_way')),
        awaiting_cash=Count('id', filter=Q(status='awaiting_cash')),
        completed=Count('id', filter=Q(status='completed')),
        declined=Count('id', filter=Q(status='declined'))
    )

    total_attempted = sum(funnel.values())
    conversion = round((funnel["completed"] / total_attempted) * 100, 1) if total_attempted > 0 else 0.0

    result = {
        "funnel": funnel,
        "conversion_rate": f"{conversion}%"
    }

    # Кешуємо на 5 хвилин
    cache.set(cache_key, result, 300)
    return Response(result)


class LeadViewSet(viewsets.ModelViewSet):
    # 🚀 МАКСИМАЛЬНА ОПТИМІЗАЦІЯ: Leads з менеджером + платежі
    queryset = Lead.objects.select_related('assigned_to').prefetch_related(
        Prefetch('payment_operations', queryset=LeadPaymentOperation.objects.order_by('-created_at'))
    ).order_by('-created_at')
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """🚀 ДОДАТКОВА ОПТИМІЗАЦІЯ: Кешування списку лідів"""
        cache_key = f"leads_list_{self.request.user.id}"
        cached_queryset = cache.get(cache_key)

        if cached_queryset is None:
            queryset = super().get_queryset()
            # Кешуємо тільки ID для уникнення проблем з сериалізацією
            cached_ids = list(queryset.values_list('id', flat=True)[:100])  # Перші 100
            cache.set(cache_key, cached_ids, 60)  # Кеш на 1 хвилину
            return queryset

        # Повертаємо оптимізований queryset на основі закешованих ID
        return self.queryset.filter(id__in=cached_queryset)

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
        """🚀 НОВА ОПТИМІЗАЦІЯ: Платежі по ліду з кешем"""
        lead = self.get_object()

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
            cache.set(cache_key, cached_payments, 300)  # 5 хвилин

        return Response(cached_payments)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """🚀 ДОДАВАННЯ ПЛАТЕЖУ З ОЧИЩЕННЯМ КЕШУ"""
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

        # 🚀 ОЧИЩУЄМО КЕШ після додавання
        cache.delete(f"lead_payments_{lead.id}")
        cache.delete(f"leads_list_{request.user.id}")

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
            'in_work': ['awaiting_prepayment', 'declined'],
            'awaiting_prepayment': ['preparation', 'declined'],
            'preparation': ['warehouse_processing', 'declined'],
            'warehouse_processing': ['on_the_way', 'declined'],
            'on_the_way': ['completed', 'declined'],
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

            # 🚀 ОЧИЩУЄМО КЕШ після зміни статусу
            cache.delete(f"leads_list_{request.user.id}")
            cache.delete(f"lead_payments_{lead.id}")
            cache.delete("funnel_None_None_None")
            cache.delete_pattern("funnel_*")
            cache.delete_pattern("leads_report_*")
            cache.delete_pattern("detailed_report_*")

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
            'in_work': ['awaiting_prepayment', 'declined'],
            'awaiting_prepayment': ['preparation', 'declined'],
            'preparation': ['warehouse_processing', 'declined'],
            'warehouse_processing': ['on_the_way', 'declined'],
            'on_the_way': ['completed', 'declined'],
            'completed': [],
            'declined': [],
        }

        status_descriptions = {
            'queued': 'У черзі до менеджера',
            'in_work': 'Обробляється менеджером',
            'awaiting_prepayment': 'Очікується аванс',
            'preparation': 'Підготовка замовлення',
            'warehouse_processing': 'Обробка на складі',
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

    # 🚀 ОПТИМІЗАЦІЯ: Кешування платежів
    cache_key = f"payments_{lead_id}_{client_id}_{op_type}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

    # 🚀 ОПТИМІЗАЦІЯ: Завантажуємо лід одразу
    payments = LeadPaymentOperation.objects.select_related('lead')

    if lead_id:
        payments = payments.filter(lead_id=lead_id)
    if client_id:
        # 🚀 ОПТИМІЗАЦІЯ: Одним запитом через JOIN
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

    # Кешуємо на 2 хвилини
    cache.set(cache_key, result, 120)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_managers(request):
    # 🚀 ОПТИМІЗАЦІЯ: Кешування списку менеджерів
    cache_key = "managers_list"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response(cached_result)

    # 🚀 ОПТИМІЗАЦІЯ: Завантажуємо user дані одразу
    managers = CustomUser.objects.select_related('user').filter(interface_type='accountant')
    serializer = ManagerSerializer(managers, many=True)

    # Кешуємо на 10 хвилин (менеджери рідко змінюються)
    cache.set(cache_key, serializer.data, 600)
    return Response(serializer.data)


class ManagerViewSet(viewsets.ModelViewSet):
    # 🚀 МАКСИМАЛЬНА ОПТИМІЗАЦІЯ: Менеджери з user даними
    queryset = CustomUser.objects.select_related('user').filter(interface_type='accountant')
    serializer_class = ManagerSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        """Додаємо request в контекст — потрібно для avatar_url"""
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def create(self, request, *args, **kwargs):
        """🚀 ОЧИЩЕННЯ КЕШУ після створення менеджера"""
        response = super().create(request, *args, **kwargs)
        cache.delete("managers_list")
        return response

    def update(self, request, *args, **kwargs):
        """🚀 ОЧИЩЕННЯ КЕШУ після оновлення менеджера"""
        response = super().update(request, *args, **kwargs)
        cache.delete("managers_list")
        return response

    def destroy(self, request, *args, **kwargs):
        """🚀 ОЧИЩЕННЯ КЕШУ після видалення менеджера"""
        response = super().destroy(request, *args, **kwargs)
        cache.delete("managers_list")
        return response


class CreateLeadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LeadSerializer(data=request.data)
        if serializer.is_valid():
            lead = serializer.save()

            # 🚀 ОЧИЩУЄМО КЕШ після створення ліда
            cache.delete(f"leads_list_{request.user.id}")

            return Response({
                "lead_id": lead.id,
                "status": lead.status,
                "full_name": lead.full_name,
                "created_at": lead.created_at
            }, status=201)
        return Response(serializer.errors, status=400)