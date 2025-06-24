# backend/signals.py - НАДІЙНА ВЕРСІЯ БЕЗ ДУБЛЮВАННЯ
"""
Django Signals для автоматизації бізнес-логіки ERP/CRM системи
ЗАХИСТ ВІД ДУБЛЮВАННЯ: використовуємо transaction.on_commit()
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import models, transaction
import logging

from .models import Lead, Client, LeadPaymentOperation, CustomUser

logger = logging.getLogger('backend.signals')

# 🛡️ ГЛОБАЛЬНИЙ ЗАХИСТ ВІД ДУБЛЮВАННЯ
_processing_leads = set()  # Множина ID лідів, що обробляються


@receiver(pre_save, sender=Lead)
def lead_pre_save(sender, instance, **kwargs):
    """
    Обробка ліда ПЕРЕД збереженням - тільки статус
    """
    # Оновлення часу зміни статусу для існуючих лідів
    if instance.pk:
        try:
            old_lead = Lead.objects.get(pk=instance.pk)
            if old_lead.status != instance.status:
                instance.status_updated_at = timezone.now()
                print(f"🔄 СИГНАЛ: Статус ліда #{instance.pk} змінено: {old_lead.status} → {instance.status}")
        except Lead.DoesNotExist:
            pass


@receiver(post_save, sender=Lead)
def lead_post_save(sender, instance, created, **kwargs):
    """
    Обробка ліда ПІСЛЯ збереження - ТІЛЬКИ для нових лідів
    """
    if created and instance.pk not in _processing_leads:
        # 🛡️ Додаємо ID в захист від дублювання
        _processing_leads.add(instance.pk)

        print(f"✅ СИГНАЛ: Лід #{instance.pk} успішно створено: {instance.full_name}")

        def process_new_lead():
            """Обробка нового ліда ПІСЛЯ завершення транзакції"""
            try:
                # 1. АВТОМАТИЧНЕ СТВОРЕННЯ КЛІЄНТА
                if instance.phone:
                    normalized_phone = Client.normalize_phone(instance.phone)

                    # 🛡️ ПОДВІЙНА ПЕРЕВІРКА на існування клієнта
                    if not Client.objects.filter(phone=normalized_phone).exists():
                        client = Client.objects.create(
                            phone=normalized_phone,
                            full_name=instance.full_name or 'Клієнт',
                            email=instance.email or '',
                        )
                        print(f"👤 СТВОРЕНО клієнта: {client.full_name} ({client.phone})")
                    else:
                        client = Client.objects.get(phone=normalized_phone)
                        print(f"👤 ЗНАЙДЕНО існуючого клієнта: {client.full_name}")

                        # Оновлюємо дані якщо порожні
                        updated = False
                        if not client.full_name or client.full_name == 'Клієнт':
                            if instance.full_name:
                                client.full_name = instance.full_name
                                updated = True
                        if not client.email and instance.email:
                            client.email = instance.email
                            updated = True

                        if updated:
                            client.save()
                            print(f"👤 ОНОВЛЕНО дані клієнта: {client.full_name}")

                # 2. АВТОМАТИЧНИЙ ПЕРЕХІД queued → in_work
                current_lead = Lead.objects.get(pk=instance.pk)
                if (current_lead.status == 'queued' and
                        current_lead.assigned_to and
                        not Lead.objects.filter(
                            assigned_to=current_lead.assigned_to,
                            status='in_work'
                        ).exclude(pk=current_lead.pk).exists()):
                    # Використовуємо update() щоб НЕ викликати сигнали знову
                    Lead.objects.filter(pk=current_lead.pk).update(
                        status='in_work',
                        status_updated_at=timezone.now()
                    )
                    print(f"🚀 Лід #{current_lead.pk} переведено в роботу")

                # Очищуємо кеш
                from django.core.cache import cache
                cache.clear()

            except Exception as e:
                print(f"❌ ПОМИЛКА обробки нового ліда: {e}")
            finally:
                # 🛡️ Видаляємо з захисту після обробки
                _processing_leads.discard(instance.pk)

        # 🚀 КЛЮЧОВЕ: Виконуємо ПІСЛЯ завершення транзакції
        transaction.on_commit(process_new_lead)

    elif not created:
        # Просто оновлення існуючого ліда
        print(f"🔄 Лід #{instance.pk} оновлено")
        from django.core.cache import cache
        cache.clear()


@receiver(post_save, sender=LeadPaymentOperation)
def payment_operation_created(sender, instance, created, **kwargs):
    """
    Обробка створення платіжної операції
    """
    if created:
        print(f"💰 ПЛАТІЖ: {instance.operation_type} {instance.amount} для ліда #{instance.lead.pk}")

        # Очищуємо кеш
        from django.core.cache import cache
        cache.clear()

        # Автозавершення при повній оплаті
        if instance.operation_type == 'received':
            def check_full_payment():
                try:
                    lead = Lead.objects.get(pk=instance.lead.pk)
                    total_received = LeadPaymentOperation.objects.filter(
                        lead=lead,
                        operation_type='received'
                    ).aggregate(total=models.Sum('amount'))['total'] or 0

                    if lead.price and total_received >= lead.price and lead.status != 'completed':
                        Lead.objects.filter(pk=lead.pk).update(
                            status='completed',
                            status_updated_at=timezone.now()
                        )
                        print(f"✅ Лід #{lead.pk} автозавершено через повну оплату")
                except Exception as e:
                    print(f"❌ Помилка автозавершення: {e}")

            transaction.on_commit(check_full_payment)


@receiver(post_save, sender=Client)
def client_saved(sender, instance, created, **kwargs):
    """
    Логування створення/оновлення клієнта
    """
    if created:
        print(f"👤 КЛІЄНТ СТВОРЕНО: {instance.full_name} ({instance.phone})")
    else:
        print(f"👤 КЛІЄНТ ОНОВЛЕНО: {instance.full_name} ({instance.phone})")


# 🚀 ФУНКЦІЯ ДЛЯ ДІАГНОСТИКИ
def check_duplicates():
    """Перевірка на дублікати для діагностики"""
    from django.db.models import Count

    # Клієнти-дублікати
    duplicate_clients = Client.objects.values('phone').annotate(
        count=Count('id')
    ).filter(count__gt=1)

    if duplicate_clients:
        print("⚠️ ЗНАЙДЕНІ ДУБЛІКАТИ КЛІЄНТІВ:")
        for dup in duplicate_clients:
            clients = Client.objects.filter(phone=dup['phone'])
            print(f"📞 {dup['phone']}: {dup['count']} дублікатів")
            for client in clients:
                print(f"   - ID: {client.id}, Ім'я: {client.full_name}")
    else:
        print("✅ Дублікатів клієнтів не знайдено")


print("📡 Надійні Django signals зареєстровано (з захистом від дублювання)!")