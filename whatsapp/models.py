# whatsapp/models.py
from django.db import models


class WhatsAppMessage(models.Model):
    DIRECTION_CHOICES = [('in', 'Incoming'), ('out', 'Outgoing')]

    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, blank=True, null=True)  # sent, delivered, failed
    external_id = models.CharField(max_length=100, blank=True, null=True)  # id від провайдера (якщо є)

    def __str__(self):
        return f"{self.get_direction_display()} | {self.phone_number}"
