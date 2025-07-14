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
    files = serializers.SerializerMethodField(read_only=True)

    # 🚀 ДОДАЄМО ПОЛЯ ДЛЯ ВАЛІДАЦІЇ СТАТУСІВ
    available_statuses = serializers.SerializerMethodField(read_only=True)
    payment_info = serializers.SerializerMethodField(read_only=True)
    next_action = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'

    def get_files(self, obj):
        """Отримуємо файли ліда"""
        try:
            return [
                {
                    'id': f.id,
                    'file': f.file.url if f.file else None,
                    'uploaded_at': f.uploaded_at
                }
                for f in obj.uploaded_files.all()
            ]
        except:
            return []

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
        """🔥 ВИПРАВЛЕНА ВАЛІДАЦІЯ СТАТУСУ"""
        # Тільки для існуючих лідів (update)
        if not self.instance:
            return value

        current_status = self.instance.status

        # Якщо статус не змінюється - все ок
        if current_status == value:
            return value

        print(f"🔍 ВАЛІДАЦІЯ СТАТУСУ: {current_status} → {value}")

        # Використовуємо валідатор
        can_transition, reason = LeadStatusValidator.can_transition(
            current_status, value, self.instance
        )

        if not can_transition:
            print(f"❌ ВАЛІДАЦІЯ НЕ ПРОЙШЛА: {reason}")

            # 🔥 ЗБЕРІГАЄМО ДЕТАЛЬНУ ІНФОРМАЦІЮ ДЛЯ VIEW
            self._status_transition_error = {
                'current_status': current_status,
                'attempted_status': value,
                'reason': reason,
                'instance': self.instance,
                'available_transitions': LeadStatusValidator.get_allowed_transitions(current_status, self.instance)
            }

            # Кидаємо спеціальний маркер
            raise serializers.ValidationError("STATUS_TRANSITION_ERROR")

        print(f"✅ ВАЛІДАЦІЯ СТАТУСУ ПРОЙШЛА")
        return value

    def validate_phone(self, value):
        """🔥 ВИПРАВЛЕНА ЛОГІКА ТЕЛЕФОНУ - тільки нормалізація, БЕЗ перевірки дублікатів!"""
        if value:
            # Просто нормалізуємо телефон
            normalized_phone = Client.normalize_phone(value)
            print(f"📞 Нормалізація телефону: {value} → {normalized_phone}")
            return normalized_phone
        return value

    def validate_order_number(self, value):
        """🔥 ВИПРАВЛЕНА ВАЛІДАЦІЯ НОМЕРА ЗАМОВЛЕННЯ - тільки дублікати номерів"""
        if value:
            print(f"🔢 Перевірка номера замовлення: {value}")

            # Для оновлення - виключаємо поточний лід
            if self.instance:
                existing = Lead.objects.filter(
                    order_number=value
                ).exclude(id=self.instance.id).first()

                if existing:
                    print(f"❌ Номер замовлення {value} вже використовується в ліді #{existing.id}")
                    raise serializers.ValidationError({
                        'type': 'DUPLICATE_ORDER_NUMBER',
                        'message': f'Номер замовлення {value} вже використовується',
                        'details': {
                            'order_number': value,
                            'existing_lead': {
                                'id': existing.id,
                                'full_name': existing.full_name,
                                'phone': existing.phone,
                                'created_at': existing.created_at
                            }
                        }
                    })
            else:
                # Для створення
                existing = Lead.objects.filter(order_number=value).first()
                if existing:
                    print(f"❌ Номер замовлення {value} вже використовується в ліді #{existing.id}")
                    raise serializers.ValidationError({
                        'type': 'DUPLICATE_ORDER_NUMBER',
                        'message': f'Номер замовлення {value} вже використовується',
                        'details': {
                            'order_number': value,
                            'existing_lead': {
                                'id': existing.id,
                                'full_name': existing.full_name,
                                'phone': existing.phone,
                                'created_at': existing.created_at
                            }
                        }
                    })

            print(f"✅ Номер замовлення {value} вільний")

        return value

    def validate_price(self, value):
        """🔥 ВАЛІДАЦІЯ ЦІНИ"""
        if value is not None and value < 0:
            raise serializers.ValidationError({
                'type': 'INVALID_PRICE',
                'message': 'Ціна не може бути від\'ємною',
                'details': {
                    'provided_value': float(value),
                    'minimum_value': 0
                }
            })
        return value

    def validate(self, attrs):
        """🔥 ЗАГАЛЬНА ВАЛІДАЦІЯ - БЕЗ перевірки телефону на дублікати"""

        # Якщо це часткове оновлення
        if self.instance and self.partial:
            print(f"📝 ЧАСТКОВЕ ОНОВЛЕННЯ ліда #{self.instance.id}")
            print(f"   Поля для оновлення: {list(attrs.keys())}")

            # Перевіряємо тільки передані поля
            if 'status' in attrs:
                new_status = attrs['status']
                print(f"   Зміна статусу на: {new_status}")

                # Спеціальна перевірка для completed
                if new_status == 'completed':
                    # Перевіряємо ціну
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

        return super().validate(attrs)

    def create(self, validated_data):
        """🔥 ВИПРАВЛЕНИЙ МЕТОД CREATE - автоматичне знаходження клієнта"""
        print(f"📝 СТВОРЕННЯ ЛІДА: {validated_data}")

        phone = validated_data.get('phone')
        full_name = validated_data.get('full_name')

        if phone:
            normalized_phone = Client.normalize_phone(phone)

            # 🔥 ЗНАХОДИМО АБО СТВОРЮЄМО КЛІЄНТА
            client, created = Client.objects.get_or_create(
                phone=normalized_phone,
                defaults={
                    'full_name': full_name or 'Клієнт',
                    'temperature': 'cold',
                    'akb_segment': 'new'
                }
            )

            if created:
                print(f"✅ Створено нового клієнта: {client.full_name} ({client.phone})")
            else:
                print(f"✅ Знайдено існуючого клієнта: {client.full_name} ({client.phone})")

                # Оновлюємо ім'я клієнта якщо воно порожнє або відрізняється
                if full_name and (not client.full_name or client.full_name == 'Клієнт'):
                    client.full_name = full_name
                    client.save()
                    print(f"   Оновлено ім'я клієнта на: {full_name}")

        # Створюємо лід
        lead = super().create(validated_data)
        print(f"✅ Лід #{lead.id} створено успішно")

        return lead

    def update(self, instance, validated_data):
        """🔥 МЕТОД UPDATE З ЛОГУВАННЯМ"""
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

    def to_representation(self, instance):
        """🔥 ДОДАЄМО КОРИСНУ ІНФОРМАЦІЮ У ВІДПОВІДЬ"""
        data = super().to_representation(instance)

        # Додаємо інформацію про клієнта
        if instance.phone:
            try:
                client = Client.objects.filter(phone=instance.phone).first()
                if client:
                    data['client_info'] = {
                        'id': client.id,
                        'full_name': client.full_name,
                        'temperature': client.temperature,
                        'akb_segment': client.akb_segment,
                        'total_spent': float(client.total_spent or 0),
                        'total_orders': client.total_orders or 0
                    }
            except:
                pass

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
    """🔥 ВИПРАВЛЕНИЙ ExternalLeadSerializer - БЕЗ перевірки телефону на дублікати"""
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
            'order_number',
        ]

    def validate_phone(self, value):
        """🔥 ТІЛЬКИ НОРМАЛІЗАЦІЯ телефону - БЕЗ перевірки дублікатів"""
        if value:
            normalized = Client.normalize_phone(value)
            print(f"📞 API: Нормалізація {value} → {normalized}")
            return normalized
        return value

    def validate_order_number(self, value):
        """🔥 ТІЛЬКИ НОМЕР ЗАМОВЛЕННЯ перевіряємо на дублікати"""
        if not value:
            return value

        existing = Lead.objects.filter(order_number=value).first()
        if existing:
            print(f"❌ API: Номер замовлення {value} вже є в ліді #{existing.id}")
            raise serializers.ValidationError({
                'type': 'DUPLICATE_ORDER_NUMBER',
                'message': f'Номер замовлення {value} вже використовується',
                'details': {
                    'order_number': value,
                    'existing_lead': {
                        'id': existing.id,
                        'full_name': existing.full_name,
                        'phone': existing.phone,
                        'created_at': existing.created_at
                    }
                }
            })

        print(f"✅ API: Номер замовлення {value} вільний")
        return value

    def create(self, validated_data):
        """🔥 АВТОМАТИЧНЕ ЗНАХОДЖЕННЯ/СТВОРЕННЯ КЛІЄНТА"""
        phone = validated_data.get('phone')
        full_name = validated_data.get('full_name')

        if phone:
            normalized_phone = Client.normalize_phone(phone)

            # Знаходимо або створюємо клієнта
            client, created = Client.objects.get_or_create(
                phone=normalized_phone,
                defaults={
                    'full_name': full_name or 'Клієнт з API',
                    'temperature': 'warm',  # З API приходять теплі ліди
                    'akb_segment': 'new'
                }
            )

            if created:
                print(f"✅ API: Створено клієнта {client.full_name}")
            else:
                print(f"✅ API: Знайдено клієнта {client.full_name}")

                # Оновлюємо ім'я якщо потрібно
                if full_name and (not client.full_name or client.full_name == 'Клієнт'):
                    client.full_name = full_name
                    client.save()

        return super().create(validated_data)




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

        # 🔥 ДОЗВОЛИ ПО СТАТУСАХ ЛІДІВ
        status_permissions = self._get_status_permissions(user, user_role)

        # 🔥 СТАТИСТИКА КОРИСТУВАЧА
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
            "permissions": all_permissions[:20],
            "role": user_role,

            # Дозволи для фронтенду
            "frontend_permissions": frontend_permissions,
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
        """🔥 ДОЗВОЛИ ПО СТАТУСАХ ЛІДІВ"""
        role_code = user_role["code"]
        all_statuses = LeadStatusValidator.STATUS_FLOW

        status_permissions = {
            "can_change_status": False,
            "allowed_transitions": {},
            "restricted_statuses": [],
            "role_limitations": {},
            "status_info": {}
        }

        if role_code == "superadmin":
            status_permissions["can_change_status"] = True
            for status in all_statuses:
                status_permissions["allowed_transitions"][status] = LeadStatusValidator.STATUS_FLOW.copy()

        elif role_code == "admin":
            status_permissions["can_change_status"] = True
            for status in all_statuses:
                allowed = LeadStatusValidator.STATUS_FLOW.copy()
                status_permissions["allowed_transitions"][status] = allowed

        elif role_code == "accountant":
            status_permissions["can_change_status"] = True
            accountant_transitions = {
                "queued": ["in_work", "declined"],
                "in_work": ["awaiting_prepayment", "queued", "declined"],
                "awaiting_prepayment": ["preparation", "in_work", "declined"],
                "preparation": ["warehouse_processing", "awaiting_prepayment", "declined"],
                "warehouse_processing": [],
                "warehouse_ready": ["on_the_way"],
                "on_the_way": ["completed", "warehouse_ready", "declined"],
                "completed": [],
                "declined": []
            }
            status_permissions["allowed_transitions"] = accountant_transitions

        elif role_code == "manager":
            status_permissions["can_change_status"] = True
            manager_transitions = {
                "queued": ["in_work", "declined"],
                "in_work": ["awaiting_prepayment", "queued", "declined"],
                "awaiting_prepayment": ["in_work", "declined"],
                "preparation": [],
                "warehouse_processing": [],
                "warehouse_ready": [],
                "on_the_way": [],
                "completed": [],
                "declined": []
            }
            status_permissions["allowed_transitions"] = manager_transitions

        elif role_code == "warehouse":
            status_permissions["can_change_status"] = True
            warehouse_transitions = {
                "queued": [],
                "in_work": [],
                "awaiting_prepayment": [],
                "preparation": [],
                "warehouse_processing": ["warehouse_ready", "preparation"],
                "warehouse_ready": ["on_the_way", "warehouse_processing"],
                "on_the_way": [],
                "completed": [],
                "declined": []
            }
            status_permissions["allowed_transitions"] = warehouse_transitions

        for status_code in all_statuses:
            status_permissions["status_info"][status_code] = {
                "code": status_code,
                "name": LeadStatusValidator.STATUS_NAMES.get(status_code, status_code),
                "can_set": status_code in status_permissions.get("allowed_transitions", {}).get("queued", []),
                "is_restricted": status_code in status_permissions.get("restricted_statuses", [])
            }

        return status_permissions

    def _determine_user_role(self, user, groups, interface_type):
        """🔥 ВИЗНАЧАЄМО РОЛЬ КОРИСТУВАЧА"""
        if user.is_superuser:
            return {"code": "superadmin", "name": "Суперадміністратор", "level": 100, "description": "Повний доступ", "color": "#e74c3c"}
        if user.is_staff:
            return {"code": "admin", "name": "Адміністратор", "level": 90, "description": "Доступ до адмінки", "color": "#9b59b6"}
        if interface_type == "accountant":
            return {"code": "accountant", "name": "Бухгалтер", "level": 80, "description": "Робота з лідами та фінансами", "color": "#3498db"}
        elif interface_type == "manager":
            return {"code": "manager", "name": "Менеджер", "level": 70, "description": "Робота з клієнтами", "color": "#2ecc71"}
        elif interface_type == "warehouse":
            return {"code": "warehouse", "name": "Складський", "level": 60, "description": "Складські операції", "color": "#f39c12"}
        return {"code": "user", "name": "Користувач", "level": 10, "description": "Базовий доступ", "color": "#95a5a6"}

    def _get_frontend_permissions(self, user, user_role, all_permissions):
        """🔥 ДОЗВОЛИ ДЛЯ ФРОНТЕНДУ"""
        permissions = {
            "leads": {"view": False, "create": False, "edit": False, "delete": False, "change_status": False},
            "clients": {"view": False, "create": False, "edit": False, "delete": False},
            "payments": {"view": False, "add": False, "edit": False},
            "reports": {"view": False, "export": False},
            "admin": {"user_management": False, "system_settings": False}
        }

        role_code = user_role["code"]

        if role_code == "superadmin":
            for category in permissions.values():
                for action in category:
                    category[action] = True
        elif role_code == "admin":
            permissions["leads"] = {"view": True, "create": True, "edit": True, "delete": True, "change_status": True}
            permissions["clients"] = {"view": True, "create": True, "edit": True, "delete": True}
            permissions["payments"] = {"view": True, "add": True, "edit": True}
            permissions["reports"] = {"view": True, "export": True}
            permissions["admin"]["user_management"] = True
        elif role_code == "accountant":
            permissions["leads"] = {"view": True, "create": True, "edit": True, "delete": False, "change_status": True}
            permissions["clients"] = {"view": True, "create": True, "edit": True, "delete": False}
            permissions["payments"] = {"view": True, "add": True, "edit": True}
            permissions["reports"] = {"view": True, "export": True}
        elif role_code == "manager":
            permissions["leads"] = {"view": True, "create": True, "edit": True, "delete": False, "change_status": True}
            permissions["clients"] = {"view": True, "create": True, "edit": True, "delete": False}
            permissions["payments"] = {"view": True, "add": False, "edit": False}
        elif role_code == "warehouse":
            permissions["leads"] = {"view": True, "create": False, "edit": False, "delete": False, "change_status": True}

        return permissions

    def _get_user_stats(self, user, user_role):
        """🔥 СТАТИСТИКА КОРИСТУВАЧА"""
        role_code = user_role["code"]
        stats = {
            "leads_assigned": 0,
            "leads_completed_today": 0,
            "leads_in_work": 0,
            "pending_tasks": 0,
            "performance_score": 0,
            "weekly_performance": []
        }

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

                # Тижнева продуктивність
                weekly_stats = []
                for i in range(7):
                    day = today - timedelta(days=i)
                    completed = user_leads.filter(
                        status="completed",
                        status_updated_at__date=day
                    ).count()
                    weekly_stats.append({"date": day.strftime("%Y-%m-%d"), "completed": completed})

                stats["weekly_performance"] = list(reversed(weekly_stats))
                weekly_total = sum(day["completed"] for day in weekly_stats)
                stats["performance_score"] = min(weekly_total * 5, 100)

            except Exception as e:
                print(f"❌ Помилка статистики для {user.username}: {e}")

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