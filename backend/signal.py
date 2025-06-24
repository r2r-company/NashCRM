from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils.timezone import now
from .models import CustomUser, Lead, LeadPaymentOperation
from backend.services.lead_queue import on_lead_closed

# === Створення CustomUser ===
@receiver(post_save, sender=User)
def create_custom_user(sender, instance, created, **kwargs):
    if created:
        CustomUser.objects.create(user=instance, interface_type='manager')


# === Зберігаємо попередній стан перед збереженням ===
_lead_previous_states = {}

@receiver(pre_save, sender=Lead)
def store_previous_lead_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            previous = Lead.objects.get(pk=instance.pk)
            _lead_previous_states[instance.pk] = {
                'status': previous.status,
            }
            if previous.status != instance.status:
                instance.status_updated_at = now()
        except Lead.DoesNotExist:
            pass


# === Реагуємо на зміну статусу ===
@receiver(post_save, sender=Lead)
def handle_lead_status_change(sender, instance, created, **kwargs):
    if created:
        return

    previous_state = _lead_previous_states.get(instance.pk)
    if not previous_state:
        return

    prev = previous_state['status']
    curr = instance.status

    if prev == curr:
        _lead_previous_states.pop(instance.pk, None)
        return

    print(f"🔄 Лід #{instance.pk} змінено: {prev} → {curr}")

    # === В Дорозі → Створюємо очікувану оплату ===
    if curr == "on_the_way":
        LeadPaymentOperation.objects.get_or_create(
            lead=instance,
            operation_type='expected',
            defaults={
                "amount": instance.price,
                "comment": f"Очікується оплата по ліду #{instance.pk}"
            }
        )
        print(f"💰 Очікується {instance.price} грн по {instance.full_name}")

    # === Завершено → Прийнято оплату ===
    elif curr == "completed":
        amount = instance.actual_cash or instance.price or 0
        LeadPaymentOperation.objects.create(
            lead=instance,
            operation_type='received',
            amount=amount,
            comment=f"Гроші отримано по ліду #{instance.pk}"
        )
        print(f"💵 Отримано {amount} грн по {instance.full_name}")

        if instance.assigned_to:
            on_lead_closed(instance)

    # === Відмовлено → Пропускаємо без грошей ===
    elif curr == "declined":
        if instance.assigned_to:
            on_lead_closed(instance)
            print(f"❌ Лід {instance.full_name} відхилено")

    _lead_previous_states.pop(instance.pk, None)



# Функція для логування змін (опціонально)
def log_lead_status_change(lead, old_status, new_status, user=None):
    """Логування змін статусу для аудиту"""
    print(f"📋 AUDIT: Лід {lead.full_name} (ID: {lead.id})")
    print(f"   Статус: {old_status} → {new_status}")
    print(f"   Користувач: {user.username if user else 'Система'}")
    print(f"   Час: {now()}")
    print(f"   Ціна: {lead.price} грн")