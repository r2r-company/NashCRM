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

from .models import Lead, Client, LeadPaymentOperation, CustomUser, ClientInteraction, ClientTask
from .validators.lead_status_validator import LeadStatusValidator

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
    Обробка ліда ПІСЛЯ збереження з новою логікою
    """
    if created and instance.pk not in _processing_leads:
        # 🛡️ Додаємо ID в захист від дублювання
        _processing_leads.add(instance.pk)

        print(f"✅ НОВИЙ ЛІД: #{instance.pk} - {instance.full_name}")

        def process_new_lead():
            """Обробка нового ліда ПІСЛЯ завершення транзакції"""
            try:
                # 1. АВТОМАТИЧНЕ СТВОРЕННЯ/ОНОВЛЕННЯ КЛІЄНТА
                if instance.phone:
                    normalized_phone = Client.normalize_phone(instance.phone)
                    client, created = Client.objects.get_or_create(
                        phone=normalized_phone,
                        defaults={
                            'full_name': instance.full_name or 'Клієнт',
                            'email': instance.email or '',
                        }
                    )

                    if created:
                        print(f"👤 СТВОРЕНО клієнта: {client.full_name}")
                    else:
                        print(f"👤 ЗНАЙДЕНО клієнта: {client.full_name}")

                # 2. АВТОМАТИЧНИЙ ПЕРЕХІД queued → in_work (З ВАЛІДАЦІЄЮ)
                current_lead = Lead.objects.get(pk=instance.pk)
                if (current_lead.status == 'queued' and
                        current_lead.assigned_to and
                        not Lead.objects.filter(
                            assigned_to=current_lead.assigned_to,
                            status='in_work'
                        ).exclude(pk=current_lead.pk).exists()):

                    # Перевіряємо чи можливий перехід
                    from backend.validators.lead_status_validator import LeadStatusValidator
                    can_transition, reason = LeadStatusValidator.can_transition(
                        'queued', 'in_work', current_lead
                    )

                    if can_transition:
                        current_lead.status = 'in_work'
                        current_lead.status_updated_at = timezone.now()
                        current_lead.save()
                        print(f"🚀 Лід #{current_lead.pk} автоматично переведено в роботу")

                from django.core.cache import cache
                cache.clear()

            except Exception as e:
                print(f"❌ ПОМИЛКА обробки нового ліда: {e}")
            finally:
                _processing_leads.discard(instance.pk)

        transaction.on_commit(process_new_lead)

    elif not created:
        print(f"🔄 ОНОВЛЕНО лід #{instance.pk}")
        from django.core.cache import cache
        cache.clear()


@receiver(post_save, sender=LeadPaymentOperation)
def payment_operation_created(sender, instance, created, **kwargs):
    """
    Обробка створення платіжної операції з автозавершенням
    """
    if created:
        print(f"💰 ПЛАТІЖ: {instance.operation_type} {instance.amount} для ліда #{instance.lead.pk}")

        # Очищуємо кеш
        from django.core.cache import cache
        cache.clear()

        # 🔥 АВТОЗАВЕРШЕННЯ ПРИ ПОВНІЙ ОПЛАТІ (ТІЛЬКИ ДЛЯ ОТРИМАНИХ КОШТІВ)
        if instance.operation_type == 'received':
            def check_full_payment():
                try:
                    lead = Lead.objects.get(pk=instance.lead.pk)

                    # Перевіряємо чи лід може бути завершений
                    if lead.status == 'on_the_way' and LeadStatusValidator.is_fully_paid(lead):
                        can_complete, reason = LeadStatusValidator.can_transition(
                            lead.status, 'completed', lead
                        )

                        if can_complete:
                            lead.status = 'completed'
                            lead.status_updated_at = timezone.now()
                            lead.save()  # ← ВИКЛИКАЄ СИГНАЛИ!

                            print(f"✅ Лід #{lead.pk} автозавершено через повну оплату")
                        else:
                            print(f"⚠️ Лід #{lead.pk} повністю оплачений, але не може бути завершений: {reason}")

                    # Логуємо поточний статус оплат
                    payment_info = LeadStatusValidator.get_payment_info(lead)
                    print(
                        f"📊 Лід #{lead.pk}: оплачено {payment_info['received']} з {payment_info['price']} грн ({payment_info['payment_percentage']}%)")

                except Exception as e:
                    print(f"❌ Помилка автозавершення: {e}")

            transaction.on_commit(check_full_payment)


@receiver(pre_save, sender=Lead)
def lead_status_change_logger(sender, instance, **kwargs):
    """
    Детальне логування змін статусів з фінансовою інформацією
    """
    if instance.pk:
        try:
            old_lead = Lead.objects.get(pk=instance.pk)

            # Якщо статус змінився
            if old_lead.status != instance.status:
                instance.status_updated_at = timezone.now()

                # Логуємо зміну з фінансовою інформацією
                payment_info = LeadStatusValidator.get_payment_info(old_lead)

                print(f"🔄 ЗМІНА СТАТУСУ ліда #{instance.pk}:")
                print(f"   📊 {old_lead.full_name} ({old_lead.phone})")
                print(
                    f"   📈 {LeadStatusValidator.STATUS_NAMES.get(old_lead.status)} → {LeadStatusValidator.STATUS_NAMES.get(instance.status)}")
                print(
                    f"   💰 Оплата: {payment_info['received']}/{payment_info['price']} грн ({payment_info['payment_percentage']}%)")

                # Попередження якщо намагаються завершити без повної оплати
                if instance.status == 'completed' and not LeadStatusValidator.is_fully_paid(old_lead):
                    print(f"⚠️ УВАГА: Завершення без повної оплати! Не вистачає {payment_info['shortage']} грн")

        except Lead.DoesNotExist:
            pass



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


# 🔥 АВТОМАТИЧНЕ ОНОВЛЕННЯ МЕТРИК КЛІЄНТА ПРИ ЗМІНІ ЛІДА
@receiver(post_save, sender=Lead)
def update_client_metrics_on_lead_change(sender, instance, created, **kwargs):
    """
    Оновлення метрик клієнта при зміні ліда
    """
    if instance.phone:
        def update_metrics():
            try:
                client = Client.objects.get(phone=instance.phone)
                client.update_client_metrics()
                print(f"📊 Оновлено метрики клієнта: {client.full_name}")
            except Client.DoesNotExist:
                print(f"⚠️ Клієнт з телефоном {instance.phone} не знайдений")

        transaction.on_commit(update_metrics)


# 🔥 АВТОМАТИЧНЕ ОНОВЛЕННЯ МЕТРИК ПРИ ПЛАТЕЖАХ
@receiver(post_save, sender=LeadPaymentOperation)
def update_client_metrics_on_payment(sender, instance, created, **kwargs):
    """
    Оновлення метрик клієнта при новому платежі
    """
    if created and instance.operation_type == 'received':
        def update_metrics():
            try:
                client = Client.objects.get(phone=instance.lead.phone)
                old_total = float(client.total_spent)
                client.update_client_metrics()
                new_total = float(client.total_spent)

                print(f"💰 Платіж {instance.amount} грн від {client.full_name}")
                print(f"   Загальна сума: {old_total} → {new_total} грн")

                # Перевіряємо чи клієнт перейшов в новий сегмент
                if client.akb_segment == 'vip' and old_total < 50000:
                    print(f"🎉 {client.full_name} став VIP клієнтом!")

            except Client.DoesNotExist:
                print(f"⚠️ Клієнт не знайдений для платежу {instance.id}")

        transaction.on_commit(update_metrics)


# 🔥 АВТОМАТИЧНЕ СТВОРЕННЯ ЗАДАЧ ДЛЯ FOLLOW-UP
@receiver(post_save, sender=ClientInteraction)
def create_follow_up_task(sender, instance, created, **kwargs):
    """
    Створення задачі для follow-up якщо потрібно
    """
    if created and instance.follow_up_date:
        def create_task():
            try:
                # Перевіряємо чи немає вже задачі на цю дату
                existing_task = ClientTask.objects.filter(
                    client=instance.client,
                    due_date__date=instance.follow_up_date.date(),
                    status__in=['pending', 'in_progress']
                ).exists()

                if not existing_task:
                    task = ClientTask.objects.create(
                        client=instance.client,
                        title=f"Follow-up по взаємодії: {instance.subject}",
                        description=f"Наступний контакт по взаємодії від {instance.created_at.strftime('%d.%m.%Y')}",
                        assigned_to=instance.client.assigned_to or instance.created_by,
                        priority='medium',
                        due_date=instance.follow_up_date
                    )
                    print(f"📅 Створено задачу follow-up для {instance.client.full_name}")

            except Exception as e:
                print(f"❌ Помилка створення задачі follow-up: {e}")

        transaction.on_commit(create_task)


# 🔥 АВТОМАТИЧНЕ ОНОВЛЕННЯ ДАТИ ОСТАННЬОГО КОНТАКТУ
@receiver(post_save, sender=ClientInteraction)
def update_last_contact_date(sender, instance, created, **kwargs):
    """
    Оновлення дати останнього контакту з клієнтом
    """
    if created:
        def update_contact_date():
            try:
                client = instance.client
                client.last_contact_date = instance.created_at

                # Також оновлюємо температуру на основі нової взаємодії
                if client.temperature == 'cold':
                    client.temperature = 'warm'
                    print(f"🌡️ {client.full_name}: cold → warm (після контакту)")

                Client.objects.filter(id=client.id).update(
                    last_contact_date=client.last_contact_date,
                    temperature=client.temperature
                )

            except Exception as e:
                print(f"❌ Помилка оновлення дати контакту: {e}")

        transaction.on_commit(update_contact_date)


# 🔥 АВТОМАТИЧНЕ ПРИЗНАЧЕННЯ МЕНЕДЖЕРА НОВОМУ КЛІЄНТУ
@receiver(post_save, sender=Client)
def auto_assign_manager_to_client(sender, instance, created, **kwargs):
    """
    Автоматичне призначення менеджера новому клієнту
    """
    if created and not instance.assigned_to:
        def assign_manager():
            try:
                from backend.services.lead_creation_service import get_free_manager

                manager = get_free_manager()
                if manager:
                    Client.objects.filter(id=instance.id).update(assigned_to=manager)
                    print(f"👤 Призначено менеджера {manager.username} клієнту {instance.full_name}")

                    # Створюємо початкову задачу для менеджера
                    ClientTask.objects.create(
                        client=instance,
                        title=f"Першій контакт з новим клієнтом: {instance.full_name}",
                        description=f"Новий клієнт зареєстрований в системі. Телефон: {instance.phone}",
                        assigned_to=manager,
                        priority='medium',
                        due_date=timezone.now() + timezone.timedelta(hours=24)
                    )
                else:
                    print(f"⚠️ Немає вільних менеджерів для клієнта {instance.full_name}")

            except Exception as e:
                print(f"❌ Помилка призначення менеджера: {e}")

        transaction.on_commit(assign_manager)


# 🔥 АВТОМАТИЧНЕ СТВОРЕННЯ ПОЧАТКОВОЇ ВЗАЄМОДІЇ
@receiver(post_save, sender=Lead)
def create_initial_interaction(sender, instance, created, **kwargs):
    """
    Створення початкової взаємодії при створенні ліда
    """
    if created:
        def create_interaction():
            try:
                client = Client.objects.get(phone=instance.phone)

                # Створюємо взаємодію тільки якщо це перший лід клієнта
                existing_interactions = ClientInteraction.objects.filter(client=client).count()
                if existing_interactions == 0:
                    ClientInteraction.objects.create(
                        client=client,
                        interaction_type='other',
                        direction='incoming',
                        subject=f"Створено лід: {instance.full_name}",
                        description=f"Новий лід від {instance.source or 'невідомого джерела'}. "
                                    f"Опис: {instance.description or 'Без опису'}",
                        outcome='follow_up',
                        created_by=instance.assigned_to or client.assigned_to
                    )
                    print(f"📝 Створено початкову взаємодію для {client.full_name}")

            except Client.DoesNotExist:
                print(f"⚠️ Клієнт не знайдений для ліда {instance.id}")
            except Exception as e:
                print(f"❌ Помилка створення взаємодії: {e}")

        transaction.on_commit(create_interaction)


# 🔥 АВТОМАТИЧНЕ ПЕРЕВЕДЕННЯ КЛІЄНТА В "ГАРЯЧІ"
@receiver(post_save, sender=Lead)
def update_client_temperature_on_repeated_leads(sender, instance, created, **kwargs):
    """
    Автоматичне підвищення температури при повторних лідах
    """
    if created:
        def update_temperature():
            try:
                client = Client.objects.get(phone=instance.phone)
                leads_count = Lead.objects.filter(phone=client.phone).count()

                # Якщо це 2-й лід - переводимо в теплі
                if leads_count == 2 and client.temperature == 'cold':
                    Client.objects.filter(id=client.id).update(temperature='warm')
                    print(f"🌡️ {client.full_name}: cold → warm (2-й лід)")

                # Якщо це 3-й лід - переводимо в гарячі
                elif leads_count >= 3 and client.temperature in ['cold', 'warm']:
                    Client.objects.filter(id=client.id).update(temperature='hot')
                    print(f"🔥 {client.full_name}: → hot (3+ лідів)")

                    # Створюємо терміновую задачу для менеджера
                    ClientTask.objects.create(
                        client=client,
                        title=f"🔥 ГАРЯЧИЙ КЛІЄНТ: {client.full_name}",
                        description=f"Клієнт створив {leads_count} лідів! Терміново зв'язатися!",
                        assigned_to=client.assigned_to or instance.assigned_to,
                        priority='urgent',
                        due_date=timezone.now() + timezone.timedelta(hours=2)
                    )

            except Client.DoesNotExist:
                pass
            except Exception as e:
                print(f"❌ Помилка оновлення температури: {e}")

        transaction.on_commit(update_temperature)


# 🔥 ПОПЕРЕДЖЕННЯ ПРО РИЗИК ВІДТОКУ
@receiver(post_save, sender=Client)
def check_churn_risk(sender, instance, created, **kwargs):
    """
    Перевірка ризику відтоку клієнта
    """
    if not created and instance.rfm_recency and instance.rfm_recency > 90:
        def create_churn_warning():
            try:
                # Перевіряємо чи немає вже задачі про ризик відтоку
                existing_task = ClientTask.objects.filter(
                    client=instance,
                    title__icontains='ризик відтоку',
                    status__in=['pending', 'in_progress']
                ).exists()

                if not existing_task and instance.total_orders > 0:
                    priority = 'high' if instance.total_spent > 10000 else 'medium'

                    ClientTask.objects.create(
                        client=instance,
                        title=f"⚠️ Ризик відтоку: {instance.full_name}",
                        description=f"Клієнт не купував {instance.rfm_recency} днів. "
                                    f"Загальна сума покупок: {instance.total_spent} грн. "
                                    f"Потрібна реактивація!",
                        assigned_to=instance.assigned_to,
                        priority=priority,
                        due_date=timezone.now() + timezone.timedelta(days=1)
                    )
                    print(f"⚠️ Створено попередження про ризик відтоку: {instance.full_name}")

            except Exception as e:
                print(f"❌ Помилка створення попередження: {e}")

        transaction.on_commit(create_churn_warning)


# 🔥 АВТОМАТИЧНЕ ЗАКРИТТЯ ЗАДАЧ ПРИ ПОКУПЦІ
@receiver(post_save, sender=LeadPaymentOperation)
def auto_complete_tasks_on_purchase(sender, instance, created, **kwargs):
    """
    Автоматичне закриття активних задач при покупці клієнта
    """
    if created and instance.operation_type == 'received':
        def complete_tasks():
            try:
                client = Client.objects.get(phone=instance.lead.phone)

                # Закриваємо задачі типу "контакт", "follow-up", "реактивація"
                tasks_to_complete = ClientTask.objects.filter(
                    client=client,
                    status__in=['pending', 'in_progress']
                ).filter(
                    Q(title__icontains='контакт') |
                    Q(title__icontains='follow-up') |
                    Q(title__icontains='реактивація') |
                    Q(title__icontains='гарячий')
                )

                completed_count = 0
                for task in tasks_to_complete:
                    task.status = 'completed'
                    task.completed_at = timezone.now()
                    task.save()
                    completed_count += 1

                if completed_count > 0:
                    print(f"✅ Автоматично закрито {completed_count} задач для {client.full_name} після покупки")

            except Client.DoesNotExist:
                pass
            except Exception as e:
                print(f"❌ Помилка автозакриття задач: {e}")

        transaction.on_commit(complete_tasks)


# 🔥 ЗВІТ ПРО ЩОДЕННУ АКТИВНІСТЬ CRM
@receiver(post_save, sender=ClientInteraction)
def daily_crm_activity_tracking(sender, instance, created, **kwargs):
    """
    Відстеження щоденної активності в CRM
    """
    if created:
        def track_activity():
            try:
                from django.core.cache import cache
                today = timezone.now().date()
                cache_key = f"crm_activity_{today}_{instance.created_by.id}"

                # Збільшуємо лічильник активності менеджера
                current_count = cache.get(cache_key, 0)
                cache.set(cache_key, current_count + 1, 86400)  # 24 години

                print(f"📈 Активність {instance.created_by.username}: {current_count + 1} взаємодій сьогодні")

            except Exception as e:
                print(f"❌ Помилка відстеження активності: {e}")

        transaction.on_commit(track_activity)


print("🚀 Розширені CRM сигнали зареєстровано!")


@receiver(post_save, sender=Lead)
def critical_states_monitor(sender, instance, created, **kwargs):
    """
    Моніторинг критичних станів лідів
    """
    if not created:  # Тільки для оновлень
        def check_critical_states():
            try:
                payment_info = LeadStatusValidator.get_payment_info(instance)

                # 🚨 Переплата
                if payment_info['overpaid'] > 0:
                    print(f"🚨 ПЕРЕПЛАТА: Лід #{instance.pk} переплачено на {payment_info['overpaid']} грн!")

                # ⚠️ Лід в дорозі але не оплачений
                if instance.status == 'on_the_way' and payment_info['shortage'] > 0:
                    print(f"⚠️ УВАГА: Лід #{instance.pk} в дорозі, але не доплачено {payment_info['shortage']} грн")

                # 💰 Лід готовий до завершення
                if (instance.status == 'on_the_way' and
                        LeadStatusValidator.is_fully_paid(instance)):
                    print(f"✅ ГОТОВО: Лід #{instance.pk} можна завершувати - повністю оплачено!")

            except Exception as e:
                print(f"❌ Помилка моніторингу: {e}")

        transaction.on_commit(check_critical_states)


print("🚀 Оновлені Django signals з фінансовим контролем зареєстровано!")