from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Lead, Client, CustomUser, LeadFile, ClientInteraction, ClientTask


class LeadFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadFile
        fields = ['id', 'file', 'uploaded_at']

class LeadSerializer(serializers.ModelSerializer):
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    files = LeadFileSerializer(many=True, read_only=True)  # ← тут

    class Meta:
        model = Lead
        fields = '__all__'


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