from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Lead, Client, CustomUser


class LeadSerializer(serializers.ModelSerializer):
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)

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
