from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, get_user_model
# Create your views here.
import requests
from django.contrib.auth.models import Permission
from django.db.models import Count, Sum, DurationField, ExpressionWrapper, F
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

from NashCRM import settings
from backend.forms import LeadsReportForm
from backend.models import CustomUser, Lead, Client, LeadPaymentOperation
from backend.serializers import LeadSerializer, ClientSerializer, ExternalLeadSerializer, MyTokenObtainPairSerializer, \
    ManagerSerializer
from backend.services.lead_creation_service import create_lead_with_logic
from datetime import datetime, timedelta


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
        custom_user = CustomUser.objects.get(user=user)

        groups = list(user.groups.values_list("name", flat=True))
        permissions = list(Permission.objects.filter(user=user).values_list("codename", flat=True))

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "interface_type": custom_user.interface_type,
                "groups": groups,
                "permissions": permissions,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "last_login": user.last_login,
                "date_joined": user.date_joined,
            }
        })

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by('-created_at')
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['get'])
    def leads(self, request, pk=None):
        client = self.get_object()
        leads = Lead.objects.filter(phone=client.phone)
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
        lead_ids = Lead.objects.filter(phone=client.phone).values_list("id", flat=True)
        payments = LeadPaymentOperation.objects.filter(lead_id__in=lead_ids)
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

    leads = Lead.objects.filter(created_at__range=(start, end))

    # Підрахунок статусів
    by_status = leads.values('status').annotate(count=Count('id'))
    status_counts = {s['status']: s['count'] for s in by_status}

    # Фінансова частина
    payments = LeadPaymentOperation.objects.filter(
        lead__in=leads
    ).values('operation_type').annotate(total=Sum('amount'))

    expected_sum = sum(p['total'] for p in payments if p['operation_type'] == 'expected')
    received_sum = sum(p['total'] for p in payments if p['operation_type'] == 'received')
    delta = expected_sum - received_sum

    return Response({
        "total": leads.count(),
        "by_status": status_counts,
        "expected_sum": expected_sum,
        "received_sum": received_sum,
        "delta": delta
    })


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

        leads = Lead.objects.all()
        if date_from:
            leads = leads.filter(created_at__date__gte=date_from)
        if date_to:
            leads = leads.filter(created_at__date__lte=date_to)

        now_date = now()

        # === Звіт по менеджерах ===
        users = User.objects.filter(id__in=leads.values_list('assigned_to', flat=True).distinct())
        managers_report = []

        for user in users:
            user_all = leads.filter(assigned_to=user)
            completed = user_all.filter(status="completed")
            completed_with_duration = completed.annotate(
                duration=ExpressionWrapper(
                    F("status_updated_at") - F("created_at"),
                    output_field=DurationField()
                )
            )
            durations = [
                l.duration.total_seconds() for l in completed_with_duration if l.duration
            ]
            avg_minutes = int(sum(durations) / len(durations) / 60) if durations else None
            conversion = round((completed.count() / user_all.count()) * 100, 1) if user_all.count() else 0
            avg_check = round((completed.aggregate(Sum("price"))["price__sum"] or 0) / completed.count(), 2) if completed.count() else 0

            managers_report.append({
                "manager": user.username,
                "total_leads": user_all.count(),
                "completed": completed.count(),
                "in_work": user_all.filter(status="in_work").count(),
                "queued": user_all.filter(status="queued").count(),
                "total_price": str(completed.aggregate(Sum("price"))["price__sum"] or 0),
                "avg_duration_minutes": avg_minutes,
                "conversion_rate": f"{conversion}%",
                "avg_check": f"{avg_check}",
            })

        # === Борги по клієнтах ===
        clients_report = []

        for client in Client.objects.all():
            # Ліди клієнта, які завершені
            cl_leads = leads.filter(phone=client.phone, status="completed")

            total_price = cl_leads.aggregate(Sum("price"))["price__sum"] or 0

            # Всі ID цих лідів
            lead_ids = cl_leads.values_list("id", flat=True)

            # Оплати типу 'received'
            total_received = LeadPaymentOperation.objects.filter(
                lead_id__in=lead_ids,
                operation_type='received'
            ).aggregate(Sum("amount"))["amount__sum"] or 0

            debt = total_price - total_received

            if debt > 0:
                clients_report.append({
                    "client": client.full_name,
                    "phone": client.phone,
                    "total_unpaid": str(debt),
                    "received": str(total_received),
                    "expected": str(total_price)
                })

        # === Найбільші боржники топ-5 ===
        top_debts = sorted(clients_report, key=lambda x: float(x['total_unpaid']), reverse=True)[:5]

        # === Воронка статусів ===
        funnel = {
            "new": leads.filter(status="new").count(),
            "queued": leads.filter(status="queued").count(),
            "in_work": leads.filter(status="in_work").count(),
            "awaiting_packaging": leads.filter(status="awaiting_packaging").count(),
            "on_the_way": leads.filter(status="on_the_way").count(),
            "awaiting_cash": leads.filter(status="awaiting_cash").count(),
            "completed": leads.filter(status="completed").count(),
        }

        # === Загальні числа
        daily_stats = {
            "new_today": Lead.objects.filter(created_at__date=now_date.date()).count(),
            "completed_today": Lead.objects.filter(status="completed", status_updated_at__date=now_date.date()).count(),
            "last_7_days": Lead.objects.filter(created_at__gte=now_date - timedelta(days=7)).count()
        }

        # === Проблемні ліди
        long_in_work = Lead.objects.filter(status="in_work", created_at__lte=now_date - timedelta(days=1))

        # Ліди, по яких немає жодної оплати received
        paid_lead_ids = LeadPaymentOperation.objects.filter(
            operation_type='received'
        ).values_list('lead_id', flat=True)

        without_cash = leads.filter(
            status="completed"
        ).exclude(id__in=paid_lead_ids)

        return Response({
            "managers": managers_report,
            "debts": clients_report,
            "top_debtors": top_debts,
            "funnel": funnel,
            "stats": daily_stats,
            "delayed_leads": list(long_in_work.values_list("id", flat=True)),
            "completed_without_cash": list(without_cash.values_list("id", flat=True)),
        })




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geocode_address(request):
    address = request.query_params.get("address")
    if not address:
        return Response({"error": "Потрібно передати параметр ?address="}, status=400)

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": settings.GOOGLE_MAPS_API_KEY
    }

    response = requests.get(url, params=params).json()
    if response["status"] != "OK":
        return Response({"error": "Нічого не знайдено або помилка Google"}, status=400)

    result = response["results"][0]
    location = result["geometry"]["location"]
    components = {c['types'][0]: c['long_name'] for c in result['address_components']}

    return Response({
        "address": result["formatted_address"],
        "lat": location["lat"],
        "lng": location["lng"],
        "country": components.get("country"),
        "city": components.get("locality") or components.get("administrative_area_level_1"),
        "postal_code": components.get("postal_code"),
        "street": components.get("route"),
    })


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

    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    manager_id = request.GET.get("manager_id")

    leads = Lead.objects.all()

    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)
    if manager_id:
        leads = leads.filter(assigned_to_id=manager_id)

    statuses = [
        "new", "queued", "in_work", "awaiting_packaging",
        "on_the_way", "awaiting_cash", "completed", "declined"
    ]

    funnel = {status: leads.filter(status=status).count() for status in statuses}

    total_attempted = sum(funnel.values())
    conversion = round((funnel["completed"] / total_attempted) * 100, 1) if total_attempted > 0 else 0.0

    return Response({
        "funnel": funnel,
        "conversion_rate": f"{conversion}%"
    })


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all().order_by('-created_at')
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]

    # GET /api/leads/<id>/payments/
    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        lead = self.get_object()
        ops = lead.payment_operations.all()
        return Response([
            {
                "id": op.id,
                "type": op.operation_type,
                "amount": float(op.amount),
                "comment": op.comment,
                "created_at": op.created_at,
            } for op in ops
        ])

    # POST /api/leads/<id>/payments/
    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        lead = self.get_object()
        amount = request.data.get("amount")
        op_type = request.data.get("operation_type")
        comment = request.data.get("comment", "")

        if not amount or not op_type:
            return Response({"error": "Потрібно amount і operation_type"}, status=400)

        op = LeadPaymentOperation.objects.create(
            lead=lead,
            operation_type=op_type,
            amount=amount,
            comment=comment
        )

        return Response({
            "message": "Платіж збережено",
            "id": op.id
        })

    # PATCH /api/leads/<id>/update_status/
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Безпечне оновлення статусу ліда"""
        lead = self.get_object()
        new_status = request.data.get('status')
        old_status = lead.status

        # 💰 Для статусу "paid" отримуємо суму оплати
        received_amount = request.data.get('received_amount')

        # 🔍 ДІАГНОСТИЧНЕ ЛОГУВАННЯ
        print(f"🔍 DEBUG: Запит на зміну статусу")
        print(f"   Лід ID: {lead.id}")
        print(f"   Поточний статус: {old_status}")
        print(f"   Новий статус: {new_status}")
        print(f"   Поточна ціна: {lead.price} (тип: {type(lead.price)})")
        if received_amount is not None:
            print(f"   Отримана сума: {received_amount}")

        if not new_status:
            return Response({
                'error': 'Параметр "status" є обов\'язковим'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Перевіряємо чи статус валідний
        valid_statuses = [choice[0] for choice in Lead.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response({
                'error': f'Невалідний статус. Доступні: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 🔒 ВАЛІДАЦІЯ ПОСЛІДОВНОСТІ СТАТУСІВ
        def validate_status_transition(from_status, to_status):
            """Перевірка дозволених переходів між статусами"""

            # Карта дозволених переходів
            allowed_transitions = {
                'new': ['queued', 'in_work', 'declined'],
                'queued': ['in_work', 'declined'],
                'in_work': ['awaiting_packaging', 'declined'],
                'awaiting_packaging': ['on_the_way', 'declined'],
                'on_the_way': ['awaiting_cash', 'paid', 'completed', 'declined'],
                'awaiting_cash': ['paid', 'completed', 'declined'],
                'paid': ['completed', 'declined'],  # З paid можна завершити остаточно
                'completed': [],  # Остаточний фінальний статус
                'declined': [],  # Фінальний статус
            }

            # Перевіряємо чи дозволений перехід
            if to_status in allowed_transitions.get(from_status, []):
                return True, None

            # Формуємо помилку з доступними варіантами
            available = allowed_transitions.get(from_status, [])
            if not available:
                return False, f'Статус "{from_status}" є фінальним. Зміна статусу неможлива.'

            return False, f'Неможливо змінити статус з "{from_status}" на "{to_status}". Доступні варіанти: {", ".join(available)}'

        # Перевіряємо перехід
        is_valid, error_message = validate_status_transition(old_status, new_status)
        if not is_valid:
            return Response({
                'error': f'❌ {error_message}',
                'code': 'INVALID_STATUS_TRANSITION',
                'current_status': old_status,
                'requested_status': new_status,
                'workflow_info': {
                    'description': 'Правильний порядок статусів',
                    'flow': [
                        'new → queued/in_work',
                        'queued → in_work',
                        'in_work → awaiting_packaging (менеджер обробив)',
                        'awaiting_packaging → on_the_way (склад відправив)',
                        'on_the_way → awaiting_cash/paid (доставлено)',
                        'awaiting_cash → paid (гроші отримано)',
                        '* declined - можна з будь-якого статусу'
                    ]
                }
            }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 🔥 ВАЛІДАЦІЯ ДЛЯ СТАТУСУ "PAID"
        if new_status == "paid":
            if received_amount is None:
                return Response({
                    'error': '❌ Для статусу "paid" потрібно вказати суму оплати в полі "received_amount"',
                    'code': 'RECEIVED_AMOUNT_REQUIRED',
                    'example': {
                        'status': 'paid',
                        'received_amount': 1500.00
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                received_amount = float(received_amount)
                if received_amount < 0:
                    return Response({
                        'error': '❌ Сума оплати не може бути від\'ємною',
                        'code': 'NEGATIVE_AMOUNT'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except (ValueError, TypeError):
                return Response({
                    'error': '❌ Невалідне значення суми. Має бути числом.',
                    'code': 'INVALID_AMOUNT_FORMAT'
                }, status=status.HTTP_400_BAD_REQUEST)

        # 🔥 ВАЛІДАЦІЯ ДЛЯ СТАТУСУ "COMPLETED"
        if new_status == "completed":
            # Для completed received_amount опціональна (доплата)
            if received_amount is not None:
                try:
                    received_amount = float(received_amount)
                    if received_amount < 0:
                        return Response({
                            'error': '❌ Сума доплати не може бути від\'ємною',
                            'code': 'NEGATIVE_AMOUNT'
                        }, status=status.HTTP_400_BAD_REQUEST)
                except (ValueError, TypeError):
                    return Response({
                        'error': '❌ Невалідне значення суми доплати. Має бути числом.',
                        'code': 'INVALID_AMOUNT_FORMAT'
                    }, status=status.HTTP_400_BAD_REQUEST)

        # 🔥 ВАЛІДАЦІЯ БІЗНЕС-ЛОГІКИ
        # Перевіряємо відправку на склад
        if new_status == "awaiting_packaging":
            current_price = float(lead.price or 0)
            print(f"🔍 DEBUG: Валідація для складу")
            print(f"   current_price = {current_price}")
            print(f"   current_price <= 0 = {current_price <= 0}")

            if current_price <= 0:
                print(f"❌ DEBUG: Валідація не пройшла - повертаємо помилку")
                return Response({
                    'error': f'❌ Не можна відправити лід на склад без вказаної суми! Поточна ціна: {current_price} грн',
                    'code': 'PRICE_REQUIRED',
                    'current_price': current_price,
                    'required_action': 'Спочатку вкажіть ціну для ліда (має бути більше 0)',
                    'lead_info': {
                        'id': lead.id,
                        'name': lead.full_name,
                        'phone': lead.phone
                    }
                }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
            else:
                print(f"✅ DEBUG: Валідація пройшла - ціна {current_price} > 0")

        # Якщо валідація пройшла - оновлюємо статус
        try:
            print(f"💾 DEBUG: Зберігаємо новий статус {new_status}")

            # Зберігаємо actual_cash для статусу paid
            if new_status == "paid":
                lead.actual_cash = received_amount
                print(f"💰 DEBUG: Зберігаємо actual_cash = {received_amount}")
            elif new_status == "completed" and received_amount is not None:
                # Для completed - це доплата, додаємо до actual_cash
                current_actual_cash = float(lead.actual_cash or 0)
                lead.actual_cash = current_actual_cash + received_amount
                print(f"💰 DEBUG: Доплата {received_amount}, загальна сума = {lead.actual_cash}")

            lead.status = new_status
            lead.save()

            # 🔥 РУЧНЕ СТВОРЕННЯ ОПЕРАЦІЙ (якщо сигнали не працюють)
            if new_status == "on_the_way":
                # Створюємо очікувану оплату
                operation, created_op = LeadPaymentOperation.objects.get_or_create(
                    lead=lead,
                    operation_type='expected',
                    defaults={
                        "amount": lead.price,
                        "comment": f"Очікується оплата за лід #{lead.id} - {lead.full_name}"
                    }
                )
                if created_op:
                    print(f"💰 ✅ СТВОРЕНО очікувану оплату: {lead.price} грн")
                else:
                    print(f"💰 ℹ️ Очікувана оплата вже існує: {operation.amount} грн")

            elif new_status == "paid":
                # Створюємо отриману оплату з вказаною сумою
                operation = LeadPaymentOperation.objects.create(
                    lead=lead,
                    operation_type='received',
                    amount=received_amount,
                    comment=f"Гроші отримано від водія: {received_amount} грн за лід #{lead.id} - {lead.full_name}"
                )
                print(f"💵 ✅ СТВОРЕНО запис отримання: {received_amount} грн")

                # Призначити наступний лід
                if lead.assigned_to:
                    from backend.services.lead_queue import on_lead_closed
                    on_lead_closed(lead)
                    print(f"🔄 Призначається наступний лід менеджеру {lead.assigned_to.username}")

            elif new_status == "completed":
                # Для статусу completed може бути доплата
                if received_amount and received_amount > 0:
                    # Створюємо запис доплати
                    operation = LeadPaymentOperation.objects.create(
                        lead=lead,
                        operation_type='received',
                        amount=received_amount,
                        comment=f"Доплата при завершенні: {received_amount} грн за лід #{lead.id} - {lead.full_name}"
                    )
                    print(f"💵 ✅ СТВОРЕНО запис доплати: {received_amount} грн")

                # Розраховуємо фінальну різницю
                expected_total = float(lead.price or 0)
                received_total = float(lead.actual_cash or 0)
                final_difference = expected_total - received_total

                print(f"📊 ФІНАЛЬНИЙ РОЗРАХУНОК:")
                print(f"   Очікувалось: {expected_total} грн")
                print(f"   Отримано: {received_total} грн")
                print(f"   Різниця: {final_difference} грн")

                # Призначити наступний лід
                if lead.assigned_to:
                    from backend.services.lead_queue import on_lead_closed
                    on_lead_closed(lead)
                    print(f"🔄 Лід остаточно завершено, призначається наступний менеджеру {lead.assigned_to.username}")

            # Підготуємо відповідь
            response_data = {
                'message': f'✅ Статус успішно змінено з "{old_status}" на "{new_status}"',
                'lead_id': lead.id,
                'lead_name': lead.full_name,
                'status_changed': {
                    'from': old_status,
                    'to': new_status
                },
                'timestamp': lead.status_updated_at,
                'operations_created': new_status in ["on_the_way", "paid"]
            }

            # Додаємо інформацію про наступні кроки
            def get_next_steps(current_status):
                next_steps = {
                    'new': ['Призначити менеджеру (queued/in_work)'],
                    'queued': ['Взяти в роботу (in_work)'],
                    'in_work': ['Обробити та відправити на склад (awaiting_packaging)'],
                    'awaiting_packaging': ['Склад відправляє товар (on_the_way)'],
                    'on_the_way': ['Товар доставлено, очікуємо оплату (awaiting_cash/paid)'],
                    'awaiting_cash': ['Отримати гроші від водія (paid)'],
                    'paid': ['✅ Лід завершено'],
                    'declined': ['❌ Лід відхилено'],
                    'completed': ['✅ Лід завершено (застарілий статус)']
                }
                return next_steps.get(current_status, [])

            response_data['next_steps'] = get_next_steps(new_status)

            # Додаємо інформацію про оплату для статусів paid і completed
            if new_status == "paid":
                response_data['payment_info'] = {
                    'received_amount': float(received_amount),
                    'expected_amount': float(lead.price or 0),
                    'difference': float(lead.price or 0) - float(received_amount),
                    'status': 'partial_payment' if float(lead.price or 0) > float(received_amount) else 'full_payment'
                }
            elif new_status == "completed":
                expected_total = float(lead.price or 0)
                received_total = float(lead.actual_cash or 0)
                final_difference = expected_total - received_total

                response_data['payment_info'] = {
                    'additional_payment': float(received_amount) if received_amount else 0,
                    'total_received': received_total,
                    'expected_amount': expected_total,
                    'final_difference': final_difference,
                    'debt_remaining': final_difference > 0
                }

            return Response(response_data)

        except Exception as e:
            print(f"❌ DEBUG: Помилка збереження: {e}")
            return Response({
                'error': f'Помилка збереження: {str(e)}',
                'code': 'SAVE_ERROR'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # PATCH /api/leads/<id>/update_price/
    @action(detail=True, methods=['patch'])
    def update_price(self, request, pk=None):
        """Швидке оновлення ціни ліда"""
        lead = self.get_object()
        new_price = request.data.get('price')

        if new_price is None:
            return Response({
                'error': 'Параметр "price" є обов\'язковим'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_price = float(new_price)
            if new_price < 0:
                return Response({
                    'error': 'Ціна не може бути від\'ємною'
                }, status=status.HTTP_400_BAD_REQUEST)

            old_price = float(lead.price or 0)
            lead.price = new_price
            lead.save()

            return Response({
                'message': f'✅ Ціна оновлена з {old_price} грн на {new_price} грн',
                'lead_id': lead.id,
                'lead_name': lead.full_name,
                'price_changed': {
                    'from': old_price,
                    'to': new_price
                },
                'can_send_to_warehouse': new_price > 0
            })

        except (ValueError, TypeError):
            return Response({
                'error': 'Невалідне значення ціни. Має бути числом.'
            }, status=status.HTTP_400_BAD_REQUEST)

    # GET /api/leads/<id>/financial_summary/
    @action(detail=True, methods=['get'])
    def financial_summary(self, request, pk=None):
        """Отримати фінансовий звіт по ліду"""
        lead = self.get_object()

        operations = lead.payment_operations.all().order_by('-created_at')

        expected_sum = sum(
            op.amount for op in operations
            if op.operation_type == 'expected'
        )
        received_sum = sum(
            op.amount for op in operations
            if op.operation_type == 'received'
        )
        balance = expected_sum - received_sum

        return Response({
            'lead_id': lead.id,
            'lead_name': lead.full_name,
            'lead_price': float(lead.price or 0),
            'expected_sum': float(expected_sum),
            'received_sum': float(received_sum),
            'balance': float(balance),
            'status': lead.status,
            'operations': [
                {
                    'id': op.id,
                    'type': op.operation_type,
                    'amount': float(op.amount),
                    'comment': op.comment,
                    'created_at': op.created_at
                }
                for op in operations
            ]
        })

    # GET /api/leads/<id>/available_statuses/
    @action(detail=True, methods=['get'])
    def available_statuses(self, request, pk=None):
        """Отримати доступні статуси для зміни"""
        lead = self.get_object()
        current_status = lead.status

        # Карта дозволених переходів
        allowed_transitions = {
            'new': ['queued', 'in_work', 'declined'],
            'queued': ['in_work', 'declined'],
            'in_work': ['awaiting_packaging', 'declined'],
            'awaiting_packaging': ['on_the_way', 'declined'],
            'on_the_way': ['awaiting_cash', 'paid', 'completed', 'declined'],
            'awaiting_cash': ['paid', 'completed', 'declined'],
            'paid': ['completed', 'declined'],  # З paid можна завершити остаточно
            'completed': [],  # Остаточний фінальний статус
            'declined': [],  # Фінальний статус
        }

        # Опис статусів
        status_descriptions = {
            'new': 'Новий лід',
            'queued': 'У черзі до менеджера',
            'in_work': 'Обробляється менеджером',
            'awaiting_packaging': 'Очікує обробки на складі',
            'on_the_way': 'Товар в дорозі до клієнта',
            'awaiting_cash': 'Очікуємо оплату від водія',
            'paid': 'Оплачено (завершено)',
            'declined': 'Відмовлено',
            'completed': 'Завершено (застарілий)'
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
                    'requires_additional_data': status_code == 'paid'  # Для paid потрібна received_amount
                }
                for status_code in available
            ],
            'is_final': len(available) == 0,
            'workflow_position': self._get_workflow_position(current_status)
        })

    def _get_workflow_position(self, status):
        """Визначити позицію в робочому процесі"""
        workflow = [
            'new',
            'queued',
            'in_work',
            'awaiting_packaging',
            'on_the_way',
            'awaiting_cash',
            'paid'
        ]

        try:
            position = workflow.index(status) + 1
            return {
                'step': position,
                'total_steps': len(workflow),
                'progress_percent': round((position / len(workflow)) * 100, 1)
            }
        except ValueError:
            if status == 'declined':
                return {'step': 'declined', 'total_steps': len(workflow), 'progress_percent': 0}
            return {'step': 'unknown', 'total_steps': len(workflow), 'progress_percent': 0}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def all_payments(request):
    lead_id = request.GET.get("lead_id")
    client_id = request.GET.get("client_id")
    op_type = request.GET.get("type")  # expected / received

    payments = LeadPaymentOperation.objects.all()

    if lead_id:
        payments = payments.filter(lead_id=lead_id)
    if client_id:
        phones = Client.objects.filter(id=client_id).values_list("phone", flat=True)
        lead_ids = Lead.objects.filter(phone__in=phones).values_list("id", flat=True)
        payments = payments.filter(lead_id__in=lead_ids)
    if op_type:
        payments = payments.filter(operation_type=op_type)

    return Response([
        {
            "id": p.id,
            "lead_id": p.lead_id,
            "type": p.operation_type,
            "amount": float(p.amount),
            "comment": p.comment,
            "created_at": p.created_at,
        } for p in payments.order_by("-created_at")
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_managers(request):
    managers = CustomUser.objects.filter(interface_type='accountant')
    serializer = ManagerSerializer(managers, many=True)
    return Response(serializer.data)



class ManagerViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.select_related('user').filter(interface_type='accountant')
    serializer_class = ManagerSerializer
    permission_classes = [IsAuthenticated]