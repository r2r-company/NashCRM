from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import CustomUser, LeadPaymentOperation, Lead
from backend.services.lead_queue import on_lead_closed
from django.utils.timezone import now


@receiver(post_save, sender=User)
def create_custom_user(sender, instance, created, **kwargs):
    if created:
        CustomUser.objects.create(user=instance, interface_type='manager')  # дефолтно


# Зберігаємо попередні стани лідів
_lead_previous_states = {}


@receiver(pre_save, sender=Lead)
def store_previous_lead_state(sender, instance, **kwargs):
    """Зберігаємо попередній стан ліда перед збереженням"""
    if instance.pk:
        try:
            previous = Lead.objects.get(pk=instance.pk)
            _lead_previous_states[instance.pk] = {
                'status': previous.status,
                'price': previous.price,
            }
            print(f"🔍 Збережено попередній стан для ліда {instance.pk}: {previous.status}")
        except Lead.DoesNotExist:
            pass

    # Оновлюємо timestamp зміни статусу
    if instance.pk:
        try:
            previous = Lead.objects.get(pk=instance.pk)
            if previous.status != instance.status:
                instance.status_updated_at = now()
                print(f"📅 Оновлено timestamp для ліда {instance.pk}: {previous.status} → {instance.status}")
        except Lead.DoesNotExist:
            pass


@receiver(post_save, sender=Lead)
def handle_lead_status_change(sender, instance, created, **kwargs):
    """Обробка зміни статусу ліда після збереження"""

    # Якщо це новий лід - не обробляємо
    if created:
        print(f"🆕 Створено новий лід {instance.pk} зі статусом {instance.status}")
        return

    # Отримуємо попередній стан
    previous_state = _lead_previous_states.get(instance.pk)
    if not previous_state:
        print(f"⚠️ Не знайдено попередній стан для ліда {instance.pk}")
        return

    previous_status = previous_state['status']
    current_status = instance.status

    # Перевіряємо чи статус змінився
    if previous_status == current_status:
        print(f"➡️ Статус ліда {instance.pk} не змінився: {current_status}")
        # Очищаємо збережений стан
        del _lead_previous_states[instance.pk]
        return

    print(f"📈 Лід {instance.full_name} (ID: {instance.pk}) змінив статус: {previous_status} → {current_status}")

    # === СТАТУС: "on_the_way" (в дорозі) - СКЛАД ВІДПРАВИВ ===
    if current_status == "on_the_way":
        # Створюємо запис "очікувана оплата"
        operation, created_op = LeadPaymentOperation.objects.get_or_create(
            lead=instance,
            operation_type='expected',
            defaults={
                "amount": instance.price,
                "comment": f"Очікується оплата за лід #{instance.id} - {instance.full_name}"
            }
        )

        if created_op:
            print(f"💰 ✅ СТВОРЕНО очікувану оплату для ліда {instance.full_name}: {instance.price} грн")
        else:
            print(f"💰 ℹ️ Очікувана оплата для ліда {instance.full_name} вже існує: {operation.amount} грн")

    # === СТАТУС: "paid" (оплачено) - ВОДІЙ ПОВЕРНУВ ГРОШІ ===
    elif current_status == "paid":
        # Створюємо запис "отримано від водія"
        # Використовуємо actual_cash (якщо вказано) або price як fallback
        amount_received = instance.actual_cash or instance.price or 0

        operation = LeadPaymentOperation.objects.create(
            lead=instance,
            operation_type='received',
            amount=amount_received,
            comment=f"Гроші отримано від водія: {amount_received} грн за лід #{instance.id} - {instance.full_name}"
        )

        print(f"💵 ✅ СТВОРЕНО запис отримання грошей для ліда {instance.full_name}: {amount_received} грн")

        # Викликаємо функцію закриття ліда (призначення наступного з черги)
        if instance.assigned_to:
            on_lead_closed(instance)
            print(
                f"🔄 Лід {instance.full_name} закрито, призначається наступний менеджеру {instance.assigned_to.username}")

    # === СТАТУС: "declined" (відмовлено) ===
    elif current_status == "declined":
        # Викликаємо функцію закриття ліда без створення платежу
        if instance.assigned_to:
            on_lead_closed(instance)
            print(
                f"❌ Лід {instance.full_name} відхилено, призначається наступний менеджеру {instance.assigned_to.username}")

    # Очищаємо збережений стан
    if instance.pk in _lead_previous_states:
        del _lead_previous_states[instance.pk]


# Функція для логування змін (опціонально)
def log_lead_status_change(lead, old_status, new_status, user=None):
    """Логування змін статусу для аудиту"""
    print(f"📋 AUDIT: Лід {lead.full_name} (ID: {lead.id})")
    print(f"   Статус: {old_status} → {new_status}")
    print(f"   Користувач: {user.username if user else 'Система'}")
    print(f"   Час: {now()}")
    print(f"   Ціна: {lead.price} грн")