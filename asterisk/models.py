from django.contrib.auth import get_user_model
from django.db import models

# Create your models here.
User = get_user_model()

class SIPAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    sip_username = models.CharField(max_length=64)
    sip_password = models.CharField(max_length=128)
    domain = models.CharField(max_length=128)
    ws_url = models.CharField(max_length=256)

    def __str__(self):
        return f"{self.user.username} SIP"