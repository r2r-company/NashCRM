from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Lead, Client, CustomUser, LeadFile

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
    class Meta:
        model = Client
        fields = '__all__'



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



class ManagerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name', allow_blank=True)
    email = serializers.EmailField(source='user.email')
    is_active = serializers.BooleanField(source='user.is_active')
    password = serializers.CharField(source='user.password', write_only=True, required=False)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'is_active',
            'interface_type', 'password'
        ]

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



