import lead as lead
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import CustomUser, LeadPaymentOperation, Lead
from backend.services.lead_queue import on_lead_closed
from django.utils.timezone import now

@receiver(post_save, sender=User)
def create_custom_user(sender, instance, created, **kwargs):
    if created:
        CustomUser.objects.create(user=instance, interface_type='manager')  # дефолтно



@receiver(post_save, sender=Lead)
def create_expected_payment(sender, instance, **kwargs):
    if instance.status == "on_the_way":
        LeadPaymentOperation.objects.get_or_create(
            lead=instance,
            operation_type='expected',
            defaults={"amount": instance.price}
        )


@receiver(post_save, sender=Lead)
def create_received_payment(sender, instance, **kwargs):
    if instance.status == "completed":
        LeadPaymentOperation.objects.create(
            lead=instance,
            operation_type='received',
            amount=instance.actual_cash or 0,
            comment="Гроші привіз водій"
        )

@receiver(pre_save, sender=Lead)
def update_status_time(sender, instance, **kwargs):
    if not instance.pk:
        return  # новий лід — пропускаємо

    try:
        previous = Lead.objects.get(pk=instance.pk)
    except Lead.DoesNotExist:
        return

    # якщо статус змінюється на in_work — оновлюємо timestamp
    if previous.status != instance.status and instance.status == "in_work":
        instance.status_updated_at = now()


lead.status = 'paid'
lead.save()

on_lead_closed(lead)