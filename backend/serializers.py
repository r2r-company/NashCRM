from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Lead, Client, CustomUser, LeadPaymentOperation


class LeadSerializer(serializers.ModelSerializer):
    # 🚀 ОПТИМІЗАЦІЯ: Використовуємо SerializerMethodField тільки коли потрібно
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'

    def to_representation(self, instance):
        """Оптимізована серіалізація з мінімальними обчисленнями"""
        data = super().to_representation(instance)

        # 🚀 Конвертуємо Decimal в float тільки один раз
        if data.get('price'):
            data['price'] = float(data['price'])
        if data.get('actual_cash'):
            data['actual_cash'] = float(data['actual_cash'])

        return data


class ClientSerializer(serializers.ModelSerializer):
    # 🚀 ОПТИМІЗАЦІЯ: Додаємо часто використовувані поля
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = Client
        fields = '__all__'

    def to_representation(self, instance):
        """Оптимізована серіалізація клієнта"""
        data = super().to_representation(instance)
        return data


class ExternalLeadSerializer(serializers.ModelSerializer):
    # 🚀 ОПТИМІЗАЦІЯ: Кешуємо queryset для менеджерів
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.select_related().all(),
        required=False
    )

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

    def validate_price(self, value):
        """Валідація ціни з бухгалтерської точки зору"""
        if value and value < 0:
            raise serializers.ValidationError("Ціна не може бути від'ємною")
        return value

    def validate_phone(self, value):
        """Нормалізація телефону як в моделі Client"""
        if value:
            from .models import Client
            return Client.normalize_phone(value)
        return value


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        # 🚀 ОПТИМІЗАЦІЯ: Одним запитом отримуємо CustomUser
        try:
            custom_user = CustomUser.objects.select_related('user').get(user=user)
            interface_type = custom_user.interface_type
            interface_label = custom_user.get_interface_type_display()
        except CustomUser.DoesNotExist:
            interface_type = None
            interface_label = None

        # 🚀 ОПТИМІЗАЦІЯ: Ефективне отримання груп
        groups = list(user.groups.values_list("name", flat=True))

        data.update({
            "username": user.username,
            "full_name": f"{user.first_name} {user.last_name}".strip(),
            "interface_type": interface_type,
            "interface_label": interface_label,
            "groups": groups,
        })
        return data


class ManagerSerializer(serializers.ModelSerializer):
    # 🚀 ОПТИМІЗАЦІЯ: Всі поля user через source
    username = serializers.CharField(source='user.username')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name', allow_blank=True)
    email = serializers.EmailField(source='user.email')
    is_active = serializers.BooleanField(source='user.is_active')
    password = serializers.CharField(source='user.password', write_only=True, required=False)

    # 🚀 ДОДАТКОВІ ПОЛЯ для аналітики менеджерів
    total_leads = serializers.SerializerMethodField()
    completed_leads = serializers.SerializerMethodField()
    conversion_rate = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'is_active',
            'interface_type', 'password', 'total_leads', 'completed_leads', 'conversion_rate'
        ]

    def get_total_leads(self, obj):
        """Загальна кількість лідів менеджера"""
        # 🚀 ОПТИМІЗАЦІЯ: Використовуємо кеш або prefetch_related
        if hasattr(obj, '_total_leads'):
            return obj._total_leads
        return getattr(obj.user, 'lead_set', Lead.objects.none()).count()

    def get_completed_leads(self, obj):
        """Кількість завершених лідів"""
        if hasattr(obj, '_completed_leads'):
            return obj._completed_leads
        return getattr(obj.user, 'lead_set', Lead.objects.none()).filter(status='completed').count()

    def get_conversion_rate(self, obj):
        """Коефіцієнт конверсії менеджера"""
        total = self.get_total_leads(obj)
        completed = self.get_completed_leads(obj)

        if total == 0:
            return "0%"

        rate = round((completed / total) * 100, 1)
        return f"{rate}%"

    def create(self, validated_data):
        """Створення менеджера з валідацією"""
        user_data = validated_data.pop('user')
        password = user_data.pop('password', None)

        # 🚀 ВАЛІДАЦІЯ даних користувача
        if not password:
            raise serializers.ValidationError("Пароль є обов'язковим при створенні")

        user = User.objects.create(**user_data)
        user.set_password(password)
        user.save()

        custom_user = CustomUser.objects.create(user=user, **validated_data)
        return custom_user

    def update(self, instance, validated_data):
        """Оновлення менеджера з валідацією"""
        user_data = validated_data.pop('user', {})
        user = instance.user

        for attr, value in user_data.items():
            if attr == 'password':
                if value:  # Оновлюємо пароль тільки якщо він переданий
                    user.set_password(value)
            else:
                setattr(user, attr, value)
        user.save()

        # Оновлюємо CustomUser
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance

    def to_representation(self, instance):
        """Оптимізована серіалізація менеджера"""
        data = super().to_representation(instance)

        # 🚀 ОПТИМІЗАЦІЯ: Видаляємо password з відповіді
        data.pop('password', None)

        return data


class LeadPaymentOperationSerializer(serializers.ModelSerializer):
    """Серіалізатор для фінансових операцій"""
    lead_name = serializers.CharField(source='lead.full_name', read_only=True)
    lead_phone = serializers.CharField(source='lead.phone', read_only=True)

    class Meta:
        model = LeadPaymentOperation
        fields = '__all__'

    def validate_amount(self, value):
        """Валідація суми операції"""
        if value <= 0:
            raise serializers.ValidationError("Сума операції має бути більше 0")
        return value

    def validate(self, data):
        """Комплексна валідація операції"""
        # 🚀 БУХГАЛТЕРСЬКА ВАЛІДАЦІЯ
        if data['operation_type'] == 'received':
            lead = data['lead']

            # Перевіряємо чи не перевищуємо очікувану суму
            total_received = LeadPaymentOperation.objects.filter(
                lead=lead,
                operation_type='received'
            ).aggregate(Sum('amount'))['amount__sum'] or 0

            if total_received + data['amount'] > lead.price:
                raise serializers.ValidationError(
                    f"Сума перевищує ціну ліда! "
                    f"Ціна: {lead.price}, вже отримано: {total_received}, "
                    f"намагаєтесь додати: {data['amount']}"
                )

        return data

    def to_representation(self, instance):
        """Оптимізована серіалізація операції"""
        data = super().to_representation(instance)

        # Конвертуємо Decimal в float
        if data.get('amount'):
            data['amount'] = float(data['amount'])

        return data


class ClientReportSerializer(serializers.Serializer):
    """Серіалізатор для звітів по клієнтах"""
    client_name = serializers.CharField()
    phone = serializers.CharField()
    total_leads = serializers.IntegerField()
    completed_leads = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_received = serializers.DecimalField(max_digits=10, decimal_places=2)
    debt = serializers.DecimalField(max_digits=10, decimal_places=2)
    last_lead_date = serializers.DateTimeField()

    def to_representation(self, instance):
        """Конвертуємо Decimal в float для JSON"""
        data = super().to_representation(instance)

        decimal_fields = ['total_revenue', 'total_received', 'debt']
        for field in decimal_fields:
            if data.get(field) is not None:
                data[field] = float(data[field])

        return data


class ManagerReportSerializer(serializers.Serializer):
    """Серіалізатор для звітів по менеджерах"""
    manager_id = serializers.IntegerField()
    manager_name = serializers.CharField()
    total_leads = serializers.IntegerField()
    completed_leads = serializers.IntegerField()
    in_work_leads = serializers.IntegerField()
    conversion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    avg_deal_size = serializers.DecimalField(max_digits=10, decimal_places=2)
    avg_close_time_hours = serializers.IntegerField(allow_null=True)

    def to_representation(self, instance):
        """Форматуємо дані для UI"""
        data = super().to_representation(instance)

        # Конвертуємо фінансові поля
        decimal_fields = ['conversion_rate', 'total_revenue', 'avg_deal_size']
        for field in decimal_fields:
            if data.get(field) is not None:
                data[field] = float(data[field])

        # Форматуємо коефіцієнт конверсії у відсотки
        if data.get('conversion_rate') is not None:
            data['conversion_rate_display'] = f"{data['conversion_rate']}%"

        return data


class FunnelDataSerializer(serializers.Serializer):
    """Серіалізатор для даних воронки продажів"""
    new = serializers.IntegerField()
    queued = serializers.IntegerField()
    in_work = serializers.IntegerField()
    awaiting_packaging = serializers.IntegerField()
    on_the_way = serializers.IntegerField()
    awaiting_cash = serializers.IntegerField()
    completed = serializers.IntegerField()
    declined = serializers.IntegerField()

    # Додаткові метрики
    total_leads = serializers.SerializerMethodField()
    conversion_rate = serializers.SerializerMethodField()
    drop_off_rate = serializers.SerializerMethodField()

    def get_total_leads(self, obj):
        """Загальна кількість лідів у воронці"""
        return sum([
            obj.get('new', 0),
            obj.get('queued', 0),
            obj.get('in_work', 0),
            obj.get('awaiting_packaging', 0),
            obj.get('on_the_way', 0),
            obj.get('awaiting_cash', 0),
            obj.get('completed', 0),
            obj.get('declined', 0),
        ])

    def get_conversion_rate(self, obj):
        """Коефіцієнт конверсії"""
        total = self.get_total_leads(obj)
        completed = obj.get('completed', 0)

        if total == 0:
            return 0.0

        return round((completed / total) * 100, 2)

    def get_drop_off_rate(self, obj):
        """Коефіцієнт відмов"""
        total = self.get_total_leads(obj)
        declined = obj.get('declined', 0)

        if total == 0:
            return 0.0

        return round((declined / total) * 100, 2)