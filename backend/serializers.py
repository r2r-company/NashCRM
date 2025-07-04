# backend/serializers.py - ОНОВЛЕНИЙ LeadSerializer

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from rest_framework import serializers
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
        """🔥 ВАЛІДАЦІЯ СТАТУСУ ПРИ ОНОВЛЕННІ"""
        # Тільки для існуючих лідів (update)
        if self.instance:
            current_status = self.instance.status

            # Якщо статус не змінюється - все ок
            if current_status == value:
                return value

            print(f"🔍 ВАЛІДАЦІЯ: {current_status} → {value}")

            # Перевіряємо чи можливий перехід
            can_transition, reason = LeadStatusValidator.can_transition(
                current_status, value, self.instance
            )

            if not can_transition:
                print(f"❌ ВАЛІДАЦІЯ НЕ ПРОЙШЛА: {reason}")

                # 🔥 ДЕТАЛЬНЕ ПОЯСНЕННЯ ДЛЯ КОРИСТУВАЧА
                available_transitions = LeadStatusValidator.get_allowed_transitions(current_status, self.instance)

                # Спеціальне пояснення для конкретних випадків
                detailed_explanation = self._get_detailed_status_explanation(current_status, value, self.instance)

                raise serializers.ValidationError({
                    'status': {
                        'error_type': 'STATUS_TRANSITION_BLOCKED',
                        'message': reason,
                        'detailed_explanation': detailed_explanation,
                        'current_status': {
                            'code': current_status,
                            'name': LeadStatusValidator.STATUS_NAMES.get(current_status)
                        },
                        'attempted_status': {
                            'code': value,
                            'name': LeadStatusValidator.STATUS_NAMES.get(value)
                        },
                        'available_statuses': [
                            {
                                'code': status,
                                'name': LeadStatusValidator.STATUS_NAMES.get(status),
                                'description': LeadStatusValidator._get_transition_description(current_status, status)
                            }
                            for status in available_transitions
                        ],
                        'required_action': LeadStatusValidator.get_next_required_action(self.instance),
                        'business_rules': self._get_business_rules_explanation(current_status, value)
                    }
                })

            print(f"✅ ВАЛІДАЦІЯ ПРОЙШЛА: {reason}")

        return value

    def validate(self, attrs):
        """Додаткова валідація для повного об'єкта"""
        # Якщо це оновлення і змінюється статус
        if self.instance and 'status' in attrs:
            new_status = attrs['status']

            # Спеціальна перевірка для completed
            if new_status == 'completed':
                # Перевіряємо чи є ціна
                price = attrs.get('price', self.instance.price)
                if not price or price <= 0:
                    raise serializers.ValidationError({
                        'status': 'Неможливо завершити лід без встановленої ціни'
                    })

                # Перевіряємо чи є повна оплата
                if not LeadStatusValidator.is_fully_paid(self.instance):
                    payment_info = LeadStatusValidator.get_payment_info(self.instance)
                    raise serializers.ValidationError({
                        'status': f'Неможливо завершити - не вистачає {payment_info["shortage"]} грн',
                        'payment_details': payment_info
                    })

        return attrs

    def update(self, instance, validated_data):
        """🔥 ПЕРЕПИСУЄМО МЕТОД UPDATE ДЛЯ ЛОГУВАННЯ"""
        old_status = instance.status
        new_status = validated_data.get('status', old_status)

        print(f"📝 СЕРІАЛІЗАТОР UPDATE: Лід #{instance.pk}")
        print(f"   Статус: {old_status} → {new_status}")

        # Виконуємо стандартне оновлення
        updated_instance = super().update(instance, validated_data)

        # Якщо статус змінився - логуємо
        if old_status != new_status:
            print(f"✅ СТАТУС ЗМІНЕНО: #{updated_instance.pk} - {old_status} → {new_status}")
            print(f"   Django signals спрацюють автоматично!")

        return updated_instance

    def _get_detailed_status_explanation(self, current_status: str, attempted_status: str, lead) -> str:
        """
        🔥 ДЕТАЛЬНЕ ПОЯСНЕННЯ ЧОМУ ПЕРЕХІД НЕМОЖЛИВИЙ
        """
        if current_status == 'preparation' and attempted_status == 'warehouse_processing':
            # Перевіряємо чи є платіжні записи
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
                    f"   POST /api/leads/{lead.id}/add-payment/\n"
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
        """
        🔥 ПОЯСНЕННЯ БІЗНЕС-ПРАВИЛ
        """
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


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        try:
            custom_user = CustomUser.objects.get(user=user)
            interface_type = custom_user.interface_type
            interface_label = custom_user.get_interface_type_display()
        except CustomUser.DoesNotExist:
            interface_type = None
            interface_label = None

        data.update({
            "username": user.username,
            "full_name": f"{user.first_name} {user.last_name}".strip(),
            "interface_type": interface_type,
            "interface_label": interface_label,
            "groups": list(user.groups.values_list("name", flat=True)),
        })
        return data


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