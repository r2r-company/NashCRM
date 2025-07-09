# backend/serializers.py - ОНОВЛЕНИЙ LeadSerializer

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Lead, Client, CustomUser, LeadFile, ClientInteraction, ClientTask
from .validators.lead_status_validator import LeadStatusValidator, validate_lead_status_change


class LeadFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadFile
        fields = ['id', 'file', 'uploaded_at']


class LeadSerializer(serializers.ModelSerializer):
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    files = LeadFileSerializer(many=True, read_only=True)

    # 🚀 ДОДАЄМО ПОЛЯ ДЛЯ ВАЛІДАЦІЇ СТАТУСІВ
    available_statuses = serializers.SerializerMethodField(read_only=True)
    payment_info = serializers.SerializerMethodField(read_only=True)
    next_action = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """🔥 АВТОМАТИЧНО РОБИМО ВСІ ПОЛЯ НЕОБОВ'ЯЗКОВИМИ ПРИ UPDATE"""
        super().__init__(*args, **kwargs)

        # Якщо це update (instance існує), робимо всі поля не обов'язковими
        if self.instance:
            for field_name, field in self.fields.items():
                # Пропускаємо read-only поля
                if not field.read_only:
                    field.required = False
                    # Дозволяємо null/blank для більшості полів
                    if hasattr(field, 'allow_null') and field_name not in ['id', 'created_at']:
                        field.allow_null = True
                    if hasattr(field, 'allow_blank') and field_name not in ['id']:
                        field.allow_blank = True

    def get_available_statuses(self, obj):
        """Доступні статуси для переходу"""
        if obj and obj.status:
            allowed = LeadStatusValidator.get_allowed_transitions(obj.status, obj)
            return [
                {
                    'code': status,
                    'name': LeadStatusValidator.STATUS_NAMES.get(status, status)
                }
                for status in allowed
            ]
        return []

    def get_payment_info(self, obj):
        """Інформація про платежі"""
        if obj:
            return LeadStatusValidator.get_payment_info(obj)
        return {}

    def get_next_action(self, obj):
        """Наступна дія для ліда"""
        if obj:
            return LeadStatusValidator.get_next_required_action(obj)
        return ""

    def validate_status(self, value):
        """🔥 ВИПРАВЛЕНА ВАЛІДАЦІЯ СТАТУСУ - помічаємо помилку для view"""
        # Тільки для існуючих лідів (update)
        if self.instance:
            current_status = self.instance.status

            # Якщо статус не змінюється - все ок
            if current_status == value:
                return value

            print(f"🔍 ВАЛІДАЦІЯ СТАТУСУ: {current_status} → {value}")

            # Перевіряємо чи можливий перехід
            can_transition, reason = LeadStatusValidator.can_transition(
                current_status, value, self.instance
            )

            if not can_transition:
                print(f"❌ ВАЛІДАЦІЯ НЕ ПРОЙШЛА: {reason}")

                # 🔥 СПЕЦІАЛЬНИЙ МАРКЕР для view щоб він зрозумів що це помилка переходу статусу
                # Зберігаємо інформацію в контексті серіалізатора
                self._status_transition_error = {
                    'current_status': current_status,
                    'attempted_status': value,
                    'reason': reason,
                    'instance': self.instance
                }

                # 🔥 КИДАЄМО ПРОСТУ ТЕКСТОВУ ПОМИЛКУ - view сам оформить
                raise serializers.ValidationError("STATUS_TRANSITION_ERROR")

            print(f"✅ ВАЛІДАЦІЯ ПРОЙШЛА: {reason}")

        return value

    def validate_phone(self, value):
        """🔥 ВАЛІДАЦІЯ ТЕЛЕФОНУ - тільки якщо поле передається"""
        if value:
            # Нормалізуємо телефон
            normalized_phone = Client.normalize_phone(value)

            # Для оновлення - перевіряємо дублікати виключаючи поточний лід
            if self.instance:
                existing = Lead.objects.filter(
                    phone=normalized_phone
                ).exclude(id=self.instance.id).first()

                if existing:
                    raise serializers.ValidationError(
                        f'Лід з таким телефоном вже існує (ID: {existing.id})'
                    )
            else:
                # Для створення - перевіряємо всі дублікати
                if Lead.objects.filter(phone=normalized_phone).exists():
                    raise serializers.ValidationError(
                        'Лід з таким телефоном вже існує'
                    )

            return normalized_phone

        return value

    def validate_order_number(self, value):
        """🔥 ВАЛІДАЦІЯ НОМЕРА ЗАМОВЛЕННЯ - тільки якщо поле передається"""
        if value:
            # Для оновлення - виключаємо поточний лід
            if self.instance:
                existing = Lead.objects.filter(
                    order_number=value
                ).exclude(id=self.instance.id).first()

                if existing:
                    raise serializers.ValidationError(
                        f'Номер замовлення вже використовується в ліді #{existing.id}'
                    )
            else:
                # Для створення
                if Lead.objects.filter(order_number=value).exists():
                    raise serializers.ValidationError(
                        'Номер замовлення вже використовується'
                    )

        return value

    def validate(self, attrs):
        """🔥 ЗАГАЛЬНА ВАЛІДАЦІЯ - тільки для переданих полів"""

        # Якщо це часткове оновлення
        if self.instance and self.partial:
            print(f"📝 ЧАСТКОВЕ ОНОВЛЕННЯ ліда #{self.instance.id}")
            print(f"   Поля для оновлення: {list(attrs.keys())}")

            # Перевіряємо тільки передані поля
            if 'status' in attrs:
                new_status = attrs['status']

                # Спеціальна перевірка для completed
                if new_status == 'completed':
                    # Перевіряємо ціну (беремо з attrs або з існуючого об'єкта)
                    price = attrs.get('price', self.instance.price)
                    if not price or price <= 0:
                        raise serializers.ValidationError({
                            'status': 'Неможливо завершити лід без встановленої ціни',
                            'current_price': float(self.instance.price or 0),
                            'solution': 'Встановіть ціну перед завершенням ліда'
                        })

                    # Перевіряємо повну оплату
                    if not LeadStatusValidator.is_fully_paid(self.instance):
                        payment_info = LeadStatusValidator.get_payment_info(self.instance)
                        raise serializers.ValidationError({
                            'status': f'Неможливо завершити - не вистачає {payment_info["shortage"]} грн',
                            'payment_details': payment_info,
                            'solution': 'Додайте недостаючі платежі'
                        })

            # Валідація ціни якщо вона змінюється
            if 'price' in attrs:
                new_price = attrs['price']
                if new_price is not None and new_price < 0:
                    raise serializers.ValidationError({
                        'price': 'Ціна не може бути від\'ємною'
                    })

        return super().validate(attrs)

    def update(self, instance, validated_data):
        """🔥 ПЕРЕПИСУЄМО МЕТОД UPDATE ДЛЯ ЛОГУВАННЯ"""
        old_status = instance.status
        old_price = float(instance.price or 0)
        old_assigned = instance.assigned_to.username if instance.assigned_to else None

        new_status = validated_data.get('status', old_status)
        new_price = validated_data.get('price', old_price)

        print(f"📝 СЕРІАЛІЗАТОР UPDATE: Лід #{instance.pk}")
        print(f"   Статус: {old_status} → {new_status}")
        print(f"   Ціна: {old_price} → {new_price}")
        print(f"   Оновлювані поля: {list(validated_data.keys())}")

        # Виконуємо стандартне оновлення
        updated_instance = super().update(instance, validated_data)

        # Логуємо зміни
        changes = []
        if old_status != new_status:
            changes.append(f"статус: {old_status} → {new_status}")
        if old_price != new_price:
            changes.append(f"ціна: {old_price} → {new_price}")

        new_assigned = updated_instance.assigned_to.username if updated_instance.assigned_to else None
        if old_assigned != new_assigned:
            changes.append(f"менеджер: {old_assigned} → {new_assigned}")

        if changes:
            print(f"✅ ЗМІНИ В ЛІДІ #{updated_instance.pk}: {', '.join(changes)}")
        else:
            print(f"ℹ️  Лід #{updated_instance.pk} оновлено без ключових змін")

        return updated_instance

    def _get_detailed_status_explanation(self, current_status: str, attempted_status: str, lead) -> str:
        """🔥 ДЕТАЛЬНЕ ПОЯСНЕННЯ ЧОМУ ПЕРЕХІД НЕМОЖЛИВИЙ"""

        if current_status == 'preparation' and attempted_status == 'warehouse_processing':
            from backend.models import LeadPaymentOperation
            has_payments = LeadPaymentOperation.objects.filter(lead=lead).exists()

            if not has_payments:
                return (
                    "❌ Неможливо передати на склад без фінансових записів!\n\n"
                    "📋 Що потрібно зробити:\n"
                    "1. Додайте запис про очікувану оплату:\n"
                    f"   POST /api/leads/{lead.id}/add-payment/\n"
                    "   {\n"
                    "     \"operation_type\": \"expected\",\n"
                    f"     \"amount\": {lead.price or 'ЦІНА_ЛІДА'},\n"
                    "     \"comment\": \"Очікується оплата від клієнта\"\n"
                    "   }\n\n"
                    "2. Після цього можна буде передати на склад\n\n"
                    "💡 Це захищає від відправки товару без фінансового контролю"
                )

        elif attempted_status == 'completed':
            payment_info = LeadStatusValidator.get_payment_info(lead)
            if payment_info['shortage'] > 0:
                return (
                    f"❌ Неможливо завершити - не вистачає {payment_info['shortage']} грн!\n\n"
                    "📋 Що потрібно зробити:\n"
                    "1. Додайте платіж від клієнта:\n"
                    f"   PATCH /api/leads/{lead.id}/add-payment/\n"
                    "   {\n"
                    "     \"operation_type\": \"received\",\n"
                    f"     \"amount\": {payment_info['shortage']},\n"
                    "     \"comment\": \"Доплата від клієнта\"\n"
                    "   }\n\n"
                    f"💰 Поточний стан оплат:\n"
                    f"   Ціна ліда: {payment_info['price']} грн\n"
                    f"   Отримано: {payment_info['received']} грн\n"
                    f"   Не вистачає: {payment_info['shortage']} грн"
                )

        elif current_status == 'queued' and attempted_status not in ['in_work', 'declined']:
            return (
                "❌ З черги можна перейти тільки в роботу або відмовити!\n\n"
                "📋 Правильна послідовність:\n"
                "1. queued → in_work (менеджер бере в роботу)\n"
                "2. in_work → awaiting_prepayment (передача на оплату)\n"
                "3. awaiting_prepayment → preparation (після отримання авансу)\n\n"
                "💡 Не можна 'перестрибувати' через етапи!"
            )

        return f"Перехід з '{LeadStatusValidator.STATUS_NAMES.get(current_status)}' в '{LeadStatusValidator.STATUS_NAMES.get(attempted_status)}' заборонений бізнес-правилами"

    def _get_business_rules_explanation(self, current_status: str, attempted_status: str) -> dict:
        """🔥 ПОЯСНЕННЯ БІЗНЕС-ПРАВИЛ"""

        rules = {
            'preparation_to_warehouse': {
                'rule': 'Перед передачею на склад потрібні фінансові записи',
                'reason': 'Захист від відправки товару без контролю оплат',
                'required': 'Мінімум один запис у LeadPaymentOperation'
            },
            'any_to_completed': {
                'rule': 'Завершення тільки при повній оплаті',
                'reason': 'Фінансовий контроль - не можна завершувати борги',
                'required': 'Сума отриманих платежів >= ціна ліда'
            },
            'sequential_flow': {
                'rule': 'Послідовний перехід по етапах',
                'reason': 'Кожен етап має свої завдання та відповідальних',
                'required': 'Не можна перестрибувати через етапи'
            }
        }

        if current_status == 'preparation' and attempted_status == 'warehouse_processing':
            return rules['preparation_to_warehouse']
        elif attempted_status == 'completed':
            return rules['any_to_completed']
        else:
            return rules['sequential_flow']

    def to_representation(self, instance):
        """🔥 ДОДАЄМО КОРИСНУ ІНФОРМАЦІЮ У ВІДПОВІДЬ"""
        data = super().to_representation(instance)

        # Додаємо інформацію чи це часткове оновлення
        if hasattr(self, '_is_partial_update'):
            data['_meta'] = {
                'partial_update': True,
                'updated_fields': getattr(self, '_updated_fields', [])
            }

        return data

# Всі інші серіалізатори залишаються без змін...
class ClientSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    temperature_display = serializers.CharField(source='get_temperature_display', read_only=True)
    akb_segment_display = serializers.CharField(source='get_akb_segment_display', read_only=True)

    # Розраховані поля
    is_akb = serializers.ReadOnlyField()
    customer_lifetime_value = serializers.ReadOnlyField()
    risk_of_churn = serializers.ReadOnlyField()
    next_contact_recommendation = serializers.ReadOnlyField()

    # Статистика
    recent_interactions_count = serializers.SerializerMethodField()
    pending_tasks_count = serializers.SerializerMethodField()
    days_since_last_contact = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            # Основні поля
            'id', 'full_name', 'phone', 'email', 'company_name',
            'type', 'status', 'assigned_to', 'assigned_to_name',

            # CRM поля
            'temperature', 'temperature_display', 'akb_segment', 'akb_segment_display',
            'total_spent', 'avg_check', 'total_orders',
            'first_purchase_date', 'last_purchase_date', 'last_contact_date',

            # Додаткові поля
            'lead_source', 'preferred_contact_method', 'country', 'city',
            'difficulty_rating', 'notes',

            # RFM
            'rfm_recency', 'rfm_frequency', 'rfm_monetary', 'rfm_score',

            # Розраховані поля
            'is_akb', 'customer_lifetime_value', 'risk_of_churn',
            'next_contact_recommendation',

            # Статистика
            'recent_interactions_count', 'pending_tasks_count',
            'days_since_last_contact',

            # Дати
            'created_at', 'updated_at'
        ]

    def get_recent_interactions_count(self, obj):
        from django.utils import timezone
        from datetime import timedelta

        return obj.interactions.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()

    def get_pending_tasks_count(self, obj):
        return obj.tasks.filter(
            status__in=['pending', 'in_progress']
        ).count()

    def get_days_since_last_contact(self, obj):
        from django.utils import timezone

        if obj.last_contact_date:
            return (timezone.now() - obj.last_contact_date).days
        return None


class ExternalLeadSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta:
        model = Lead
        fields = [
            'full_name',
            'phone',
            'email',
            'source',
            'description',
            'price',
            'assigned_to',
        ]


# backend/serializers.py - Доповнення MyTokenObtainPairSerializer

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        from django.utils import timezone
        from django.contrib.auth.models import Permission
        from backend.validators.lead_status_validator import LeadStatusValidator

        data = super().validate(attrs)
        user = self.user

        # 🔥 ОСНОВНА ІНФОРМАЦІЯ ПРО КОРИСТУВАЧА
        try:
            custom_user = CustomUser.objects.get(user=user)
            interface_type = custom_user.interface_type
            interface_label = custom_user.get_interface_type_display()
            avatar_url = custom_user.avatar.url if custom_user.avatar else None
        except CustomUser.DoesNotExist:
            interface_type = None
            interface_label = None
            avatar_url = None

        # 🔥 ДЕТАЛЬНА ІНФОРМАЦІЯ ПРО РОЛІ ТА ДОЗВОЛИ
        user_groups = list(user.groups.values_list("name", flat=True))
        user_permissions = list(user.user_permissions.values_list("codename", flat=True))

        # Отримуємо всі дозволи через групи
        group_permissions = Permission.objects.filter(
            group__user=user
        ).values_list("codename", flat=True)
        all_permissions = list(set(user_permissions + list(group_permissions)))

        # 🔥 ВИЗНАЧАЄМО РОЛЬ КОРИСТУВАЧА
        user_role = self._determine_user_role(user, user_groups, interface_type)

        # 🔥 ДОЗВОЛИ ДЛЯ ФРОНТЕНДУ
        frontend_permissions = self._get_frontend_permissions(user, user_role, all_permissions)

        # 🔥 НОВИЙ БЛОК: ДОЗВОЛИ ПО СТАТУСАХ ЛІДІВ
        status_permissions = self._get_status_permissions(user, user_role)

        # 🔥 СТАТИСТИКА КОРИСТУВАЧА (якщо менеджер)
        user_stats = self._get_user_stats(user, user_role)

        # 🔥 ОНОВЛЮЄМО ВІДПОВІДЬ
        data.update({
            # Базова інформація
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": f"{user.first_name} {user.last_name}".strip() or user.username,

            # Системна інформація
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "is_active": user.is_active,
            "date_joined": user.date_joined,
            "last_login": user.last_login,

            # Кастомна інформація
            "interface_type": interface_type,
            "interface_label": interface_label,
            "avatar_url": avatar_url,

            # Ролі та дозволи
            "groups": user_groups,
            "permissions": all_permissions[:20],  # Обмежуємо кількість
            "role": user_role,

            # Дозволи для фронтенду
            "frontend_permissions": frontend_permissions,

            # 🔥 НОВИЙ БЛОК: ДОЗВОЛИ ПО СТАТУСАХ
            "status_permissions": status_permissions,

            # Статистика
            "stats": user_stats,

            # Мета-інформація
            "_meta": {
                "login_time": timezone.now(),
                "permissions_count": len(all_permissions),
                "groups_count": len(user_groups),
                "role_level": user_role["level"],
                "interface_configured": interface_type is not None,
                "status_permissions_included": True
            }
        })

        return data

    def _get_status_permissions(self, user, user_role):
        """🔥 НОВИЙ МЕТОД: Дозволи по статусах лідів"""

        role_code = user_role["code"]

        # Всі можливі статуси з валідатора
        all_statuses = LeadStatusValidator.STATUS_FLOW

        # Базова структура дозволів
        status_permissions = {
            "can_change_status": False,
            "allowed_transitions": {},
            "restricted_statuses": [],
            "role_limitations": {},
            "status_info": {}
        }

        # 🔥 ДОЗВОЛИ ЗА РОЛЯМИ
        if role_code == "superadmin":
            # Суперадмін - може все
            status_permissions["can_change_status"] = True
            for status in all_statuses:
                status_permissions["allowed_transitions"][status] = LeadStatusValidator.STATUS_FLOW.copy()

        elif role_code == "admin":
            # Адміністратор - може майже все, крім складських операцій
            status_permissions["can_change_status"] = True
            for status in all_statuses:
                allowed = LeadStatusValidator.STATUS_FLOW.copy()
                # Адмін не може безпосередньо керувати складськими процесами
                if status == "warehouse_processing":
                    allowed = ["warehouse_ready", "preparation"]  # Тільки готовність або повернення
                status_permissions["allowed_transitions"][status] = allowed

        elif role_code == "accountant":
            # Бухгалтер - може міняти фінансові та адміністративні статуси
            status_permissions["can_change_status"] = True

            accountant_transitions = {
                "queued": ["in_work", "declined"],
                "in_work": ["awaiting_prepayment", "queued", "declined"],
                "awaiting_prepayment": ["preparation", "in_work", "declined"],
                "preparation": ["warehouse_processing", "awaiting_prepayment", "declined"],
                "warehouse_processing": [],  # Не може керувати складом
                "warehouse_ready": ["on_the_way"],  # Може відправляти
                "on_the_way": ["completed", "warehouse_ready", "declined"],  # Може завершувати
                "completed": [],  # Не може змінювати завершені
                "declined": []  # Не може змінювати відмовлені
            }

            status_permissions["allowed_transitions"] = accountant_transitions
            status_permissions["restricted_statuses"] = ["warehouse_processing"]
            status_permissions["role_limitations"] = {
                "warehouse_operations": False,
                "can_complete": True,
                "can_decline": True,
                "financial_control": True
            }

        elif role_code == "manager":
            # Менеджер - тільки початкові етапи
            status_permissions["can_change_status"] = True

            manager_transitions = {
                "queued": ["in_work", "declined"],
                "in_work": ["awaiting_prepayment", "queued", "declined"],
                "awaiting_prepayment": ["in_work", "declined"],
                "preparation": [],  # Не може після передачі адміну
                "warehouse_processing": [],
                "warehouse_ready": [],
                "on_the_way": [],
                "completed": [],
                "declined": []
            }

            status_permissions["allowed_transitions"] = manager_transitions
            status_permissions["restricted_statuses"] = [
                "preparation", "warehouse_processing", "warehouse_ready", "on_the_way", "completed"
            ]
            status_permissions["role_limitations"] = {
                "warehouse_operations": False,
                "can_complete": False,
                "can_decline": True,
                "max_status": "awaiting_prepayment",
                "description": "Менеджер працює тільки з початковими етапами"
            }

        elif role_code == "warehouse":
            # Складський - тільки складські операції
            status_permissions["can_change_status"] = True

            warehouse_transitions = {
                "queued": [],
                "in_work": [],
                "awaiting_prepayment": [],
                "preparation": [],
                "warehouse_processing": ["warehouse_ready", "preparation"],  # Може готувати або повертати
                "warehouse_ready": ["on_the_way", "warehouse_processing"],  # Може відправляти або повертати
                "on_the_way": [],
                "completed": [],
                "declined": []
            }

            status_permissions["allowed_transitions"] = warehouse_transitions
            status_permissions["restricted_statuses"] = [
                "queued", "in_work", "awaiting_prepayment", "preparation", "on_the_way", "completed", "declined"
            ]
            status_permissions["role_limitations"] = {
                "warehouse_operations": True,
                "can_complete": False,
                "can_decline": False,
                "allowed_statuses": ["warehouse_processing", "warehouse_ready"],
                "description": "Складський працює тільки зі складськими операціями"
            }

        else:
            # Звичайний користувач - нічого не може
            status_permissions["can_change_status"] = False
            status_permissions["role_limitations"] = {
                "description": "Немає дозволів на зміну статусів"
            }

        # 🔥 ДОДАЄМО ІНФОРМАЦІЮ ПРО СТАТУСИ
        for status_code in all_statuses:
            status_permissions["status_info"][status_code] = {
                "code": status_code,
                "name": LeadStatusValidator.STATUS_NAMES.get(status_code, status_code),
                "can_set": status_code in status_permissions.get("allowed_transitions", {}).get("queued", []),
                "is_restricted": status_code in status_permissions.get("restricted_statuses", [])
            }

        # 🔥 ДОДАЄМО БІЗНЕС-ПРАВИЛА
        status_permissions["business_rules"] = {
            "requires_payment_for_completion": True,
            "requires_price_for_warehouse": True,
            "sequential_flow_required": True,
            "warehouse_financial_control": True,
            "description": "Статуси змінюються послідовно з фінансовим контролем"
        }

        return status_permissions

    def _determine_user_role(self, user, groups, interface_type):
        """🔥 ВИЗНАЧАЄМО РОЛЬ КОРИСТУВАЧА"""

        # Суперадмін
        if user.is_superuser:
            return {
                "code": "superadmin",
                "name": "Суперадміністратор",
                "level": 100,
                "description": "Повний доступ до всіх функцій системи",
                "color": "#e74c3c"
            }

        # Адміністратор
        if user.is_staff:
            return {
                "code": "admin",
                "name": "Адміністратор",
                "level": 90,
                "description": "Доступ до адмінки та звітів",
                "color": "#9b59b6"
            }

        # За interface_type
        if interface_type == "accountant":
            return {
                "code": "accountant",
                "name": "Бухгалтер",
                "level": 80,
                "description": "Робота з лідами та фінансами",
                "color": "#3498db"
            }
        elif interface_type == "manager":
            return {
                "code": "manager",
                "name": "Менеджер",
                "level": 70,
                "description": "Робота з клієнтами та лідами",
                "color": "#2ecc71"
            }
        elif interface_type == "warehouse":
            return {
                "code": "warehouse",
                "name": "Складський",
                "level": 60,
                "description": "Робота зі складськими операціями",
                "color": "#f39c12"
            }

        # За групами
        if "Managers" in groups or "managers" in groups:
            return {
                "code": "manager",
                "name": "Менеджер",
                "level": 70,
                "description": "Робота з клієнтами та лідами",
                "color": "#2ecc71"
            }
        elif "Accountants" in groups or "accountants" in groups:
            return {
                "code": "accountant",
                "name": "Бухгалтер",
                "level": 80,
                "description": "Робота з лідами та фінансами",
                "color": "#3498db"
            }

        # Звичайний користувач
        return {
            "code": "user",
            "name": "Користувач",
            "level": 10,
            "description": "Базовий доступ",
            "color": "#95a5a6"
        }

    def _get_frontend_permissions(self, user, user_role, all_permissions):
        """🔥 ДОЗВОЛИ ДЛЯ ФРОНТЕНДУ (залишається без змін)"""

        permissions = {
            # Ліди
            "leads": {
                "view": False,
                "create": False,
                "edit": False,
                "delete": False,
                "change_status": False,
                "assign_manager": False,
                "view_payments": False
            },

            # Клієнти
            "clients": {
                "view": False,
                "create": False,
                "edit": False,
                "delete": False,
                "view_analytics": False,
                "export": False
            },

            # Платежі
            "payments": {
                "view": False,
                "add": False,
                "edit": False,
                "delete": False
            },

            # Звіти
            "reports": {
                "view": False,
                "export": False,
                "detailed": False,
                "financial": False
            },

            # Адмін функції
            "admin": {
                "user_management": False,
                "system_settings": False,
                "database_access": False,
                "logs": False
            },

            # Менеджмент
            "management": {
                "assign_leads": False,
                "bulk_operations": False,
                "team_stats": False,
                "dashboard": False
            },

            # Інтерфейс
            "ui": {
                "admin_panel": False,
                "advanced_filters": False,
                "bulk_edit": False,
                "export_data": False
            }
        }

        role_code = user_role["code"]

        # 🔥 НАЛАШТУВАННЯ ДОЗВОЛІВ ЗА РОЛЯМИ
        if role_code == "superadmin":
            # Суперадмін - все дозволено
            for category in permissions.values():
                for action in category:
                    category[action] = True

        elif role_code == "admin":
            # Адміністратор
            permissions["leads"] = {
                "view": True, "create": True, "edit": True, "delete": True,
                "change_status": True, "assign_manager": True, "view_payments": True
            }
            permissions["clients"] = {
                "view": True, "create": True, "edit": True, "delete": True,
                "view_analytics": True, "export": True
            }
            permissions["payments"] = {
                "view": True, "add": True, "edit": True, "delete": False
            }
            permissions["reports"] = {
                "view": True, "export": True, "detailed": True, "financial": True
            }
            permissions["admin"]["user_management"] = True
            permissions["admin"]["logs"] = True
            permissions["management"] = {
                "assign_leads": True, "bulk_operations": True,
                "team_stats": True, "dashboard": True
            }
            permissions["ui"] = {
                "admin_panel": True, "advanced_filters": True,
                "bulk_edit": True, "export_data": True
            }

        elif role_code == "accountant":
            # Бухгалтер
            permissions["leads"] = {
                "view": True, "create": True, "edit": True, "delete": False,
                "change_status": True, "assign_manager": False, "view_payments": True
            }
            permissions["clients"] = {
                "view": True, "create": True, "edit": True, "delete": False,
                "view_analytics": True, "export": True
            }
            permissions["payments"] = {
                "view": True, "add": True, "edit": True, "delete": False
            }
            permissions["reports"] = {
                "view": True, "export": True, "detailed": False, "financial": True
            }
            permissions["management"]["dashboard"] = True
            permissions["ui"] = {
                "admin_panel": False, "advanced_filters": True,
                "bulk_edit": False, "export_data": True
            }

        elif role_code == "manager":
            # Менеджер
            permissions["leads"] = {
                "view": True, "create": True, "edit": True, "delete": False,
                "change_status": True, "assign_manager": False, "view_payments": False
            }
            permissions["clients"] = {
                "view": True, "create": True, "edit": True, "delete": False,
                "view_analytics": False, "export": False
            }
            permissions["payments"] = {
                "view": True, "add": False, "edit": False, "delete": False
            }
            permissions["reports"] = {
                "view": False, "export": False, "detailed": False, "financial": False
            }
            permissions["management"]["dashboard"] = True
            permissions["ui"] = {
                "admin_panel": False, "advanced_filters": False,
                "bulk_edit": False, "export_data": False
            }

        elif role_code == "warehouse":
            # Складський
            permissions["leads"] = {
                "view": True, "create": False, "edit": False, "delete": False,
                "change_status": True, "assign_manager": False, "view_payments": False
            }
            permissions["ui"]["advanced_filters"] = False

        # 🔥 ДОДАТКОВО ПЕРЕВІРЯЄМО КОНКРЕТНІ ДОЗВОЛИ Django
        if "change_lead" in all_permissions:
            permissions["leads"]["edit"] = True
        if "delete_lead" in all_permissions:
            permissions["leads"]["delete"] = True
        if "view_client" in all_permissions:
            permissions["clients"]["view"] = True
        if "add_leadpaymentoperation" in all_permissions:
            permissions["payments"]["add"] = True

        return permissions

    def _get_user_stats(self, user, user_role):
        """🔥 СТАТИСТИКА КОРИСТУВАЧА (залишається без змін)"""

        role_code = user_role["code"]
        stats = {
            "leads_assigned": 0,
            "leads_completed_today": 0,
            "leads_in_work": 0,
            "pending_tasks": 0,
            "performance_score": 0,
            "weekly_performance": []
        }

        # Тільки для менеджерів та бухгалтерів
        if role_code in ["manager", "accountant", "admin", "superadmin"]:
            try:
                from django.utils import timezone
                from datetime import timedelta

                today = timezone.now().date()

                # Статистика по лідах
                user_leads = Lead.objects.filter(assigned_to=user)
                stats["leads_assigned"] = user_leads.count()
                stats["leads_completed_today"] = user_leads.filter(
                    status="completed",
                    status_updated_at__date=today
                ).count()
                stats["leads_in_work"] = user_leads.filter(
                    status__in=["in_work", "preparation", "awaiting_prepayment"]
                ).count()

                # Задачі (якщо є модель ClientTask)
                try:
                    stats["pending_tasks"] = ClientTask.objects.filter(
                        assigned_to=user,
                        status__in=["pending", "in_progress"]
                    ).count()
                except:
                    pass

                # Тижнева продуктивність (останні 7 днів)
                weekly_stats = []
                for i in range(7):
                    day = today - timedelta(days=i)
                    completed = user_leads.filter(
                        status="completed",
                        status_updated_at__date=day
                    ).count()
                    weekly_stats.append({
                        "date": day.strftime("%Y-%m-%d"),
                        "completed": completed
                    })

                stats["weekly_performance"] = list(reversed(weekly_stats))

                # Простий розрахунок продуктивності (на основі тижневих результатів)
                weekly_total = sum(day["completed"] for day in weekly_stats)
                stats["performance_score"] = min(weekly_total * 5, 100)  # Максимум 100

            except Exception as e:
                # Якщо помилка - повертаємо порожню статистику
                print(f"❌ Помилка при отриманні статистики для {user.username}: {e}")

        return stats


User = get_user_model()


class ManagerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name', allow_blank=True)
    email = serializers.EmailField(source='user.email')
    is_active = serializers.BooleanField(source='user.is_active')
    password = serializers.CharField(source='user.password', write_only=True, required=False)

    avatar = serializers.ImageField(required=False, allow_null=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'is_active',
            'interface_type', 'avatar', 'avatar_url', 'password'
        ]

    def get_avatar_url(self, obj):
        request = self.context.get('request')
        if obj.avatar and hasattr(obj.avatar, 'url'):
            return request.build_absolute_uri(obj.avatar.url)
        return None

    def create(self, validated_data):
        user_data = validated_data.pop('user')
        password = user_data.pop('password', None)
        user = User.objects.create(**user_data)
        if password:
            user.set_password(password)
            user.save()
        return CustomUser.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        user = instance.user
        for attr, value in user_data.items():
            if attr == 'password':
                user.set_password(value)
            else:
                setattr(user, attr, value)
        user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'user', 'interface_type', 'avatar']


class ClientInteractionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)

    class Meta:
        model = ClientInteraction
        fields = [
            'id', 'client', 'client_name', 'client_phone',
            'interaction_type', 'direction', 'subject', 'description',
            'outcome', 'created_by', 'created_by_name', 'created_at',
            'follow_up_date'
        ]
        read_only_fields = ['created_by', 'created_at']


class ClientTaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = ClientTask
        fields = [
            'id', 'client', 'client_name', 'client_phone',
            'title', 'description', 'assigned_to', 'assigned_to_name',
            'priority', 'status', 'due_date', 'created_at',
            'completed_at', 'is_overdue'
        ]

    def get_is_overdue(self, obj):
        from django.utils import timezone
        return obj.due_date < timezone.now() and obj.status not in ['completed', 'cancelled']


# 🔥 КОМПАКТНИЙ СЕРІАЛІЗАТОР ДЛЯ СПИСКІВ
class ClientCompactSerializer(serializers.ModelSerializer):
    temperature_display = serializers.CharField(source='get_temperature_display', read_only=True)
    akb_segment_display = serializers.CharField(source='get_akb_segment_display', read_only=True)

    class Meta:
        model = Client
        fields = [
            'id', 'full_name', 'phone', 'temperature', 'temperature_display',
            'akb_segment', 'akb_segment_display', 'total_spent', 'total_orders',
            'last_purchase_date', 'rfm_score'
        ]


# 🔥 СЕРІАЛІЗАТОР ДЛЯ ШВИДКОГО СТВОРЕННЯ ВЗАЄМОДІЇ
class QuickInteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientInteraction
        fields = [
            'client', 'interaction_type', 'direction',
            'subject', 'description', 'outcome', 'follow_up_date'
        ]

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


# 🔥 СЕРІАЛІЗАТОР ДЛЯ ЕКСПОРТУ КЛІЄНТІВ
class ClientExportSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    temperature_display = serializers.CharField(source='get_temperature_display', read_only=True)
    akb_segment_display = serializers.CharField(source='get_akb_segment_display', read_only=True)

    class Meta:
        model = Client
        fields = [
            'id', 'full_name', 'phone', 'email', 'company_name',
            'temperature_display', 'akb_segment_display',
            'total_spent', 'avg_check', 'total_orders',
            'first_purchase_date', 'last_purchase_date',
            'rfm_score', 'assigned_to_name', 'created_at'
        ]