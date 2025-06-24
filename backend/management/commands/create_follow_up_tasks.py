# backend/management/commands/create_follow_up_tasks.py
"""
Команда для автоматичного створення задач follow-up
Використання: python manage.py create_follow_up_tasks
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from backend.models import Client, ClientTask


class Command(BaseCommand):
    help = 'Створює задачі follow-up для клієнтів що потребують уваги'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-inactive',
            type=int,
            default=90,
            help='Кількість днів неактивності для сплячих клієнтів (за замовчуванням: 90)'
        )

    def handle(self, *args, **options):
        days_inactive = options['days_inactive']

        self.stdout.write(f"🎯 Пошук клієнтів для follow-up...")

        # Сплячі клієнти
        sleeping_clients = Client.objects.filter(
            temperature='sleeping',
            total_orders__gt=0,
            rfm_recency__gte=days_inactive
        ).exclude(
            tasks__status__in=['pending', 'in_progress'],
            tasks__title__icontains='реактивація'
        )

        # Гарячі ліди
        hot_leads = Client.objects.filter(
            temperature='hot'
        ).exclude(
            tasks__status__in=['pending', 'in_progress'],
            tasks__title__icontains='контакт'
        )

        # Клієнти VIP без контакту більше місяця
        vip_no_contact = Client.objects.filter(
            akb_segment='vip',
            last_contact_date__lt=timezone.now() - timedelta(days=30)
        ).exclude(
            tasks__status__in=['pending', 'in_progress']
        )

        created_tasks = []

        # Створюємо задачі для сплячих клієнтів
        for client in sleeping_clients:
            task = ClientTask.objects.create(
                client=client,
                title=f'Реактивація клієнта: {client.full_name}',
                description=f'Клієнт не купував {client.rfm_recency} днів. '
                            f'Загальна сума покупок: {client.total_spent} грн.',
                assigned_to=client.assigned_to,
                priority='medium',
                due_date=timezone.now() + timedelta(days=3)
            )
            created_tasks.append(task)
            self.stdout.write(f"😴 Реактивація: {client.full_name}")

        # Створюємо задачі для гарячих лідів
        for client in hot_leads:
            task = ClientTask.objects.create(
                client=client,
                title=f'🔥 ТЕРМІНОВИЙ контакт: {client.full_name}',
                description=f'Гарячий лід! {client.next_contact_recommendation}',
                assigned_to=client.assigned_to,
                priority='urgent',
                due_date=timezone.now() + timedelta(hours=24)
            )
            created_tasks.append(task)
            self.stdout.write(f"🔥 Гарячий лід: {client.full_name}")

        # Створюємо задачі для VIP клієнтів
        for client in vip_no_contact:
            task = ClientTask.objects.create(
                client=client,
                title=f'💎 VIP підтримка: {client.full_name}',
                description=f'VIP клієнт без контакту більше місяця. '
                            f'Загальна сума: {client.total_spent} грн.',
                assigned_to=client.assigned_to,
                priority='high',
                due_date=timezone.now() + timedelta(days=1)
            )
            created_tasks.append(task)
            self.stdout.write(f"💎 VIP підтримка: {client.full_name}")

        # Підсумок
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Створено {len(created_tasks)} задач:\n"
                f"   Реактивація: {sleeping_clients.count()}\n"
                f"   Гарячі ліди: {hot_leads.count()}\n"
                f"   VIP підтримка: {vip_no_contact.count()}"
            )
        )