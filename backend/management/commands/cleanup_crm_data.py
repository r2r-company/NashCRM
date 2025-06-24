# backend/management/commands/cleanup_crm_data.py
"""
Команда для очищення застарілих CRM даних
Використання: python manage.py cleanup_crm_data
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from backend.models import ClientInteraction, ClientTask


class Command(BaseCommand):
    help = 'Очищує застарілі CRM дані'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Видалити дані старші за N днів (за замовчуванням: 365)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показати що буде видалено без фактичного видалення'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        cutoff_date = timezone.now() - timedelta(days=days)

        self.stdout.write(f"🧹 Очищення даних старіших за {cutoff_date.date()}")

        # Застарілі взаємодії
        old_interactions = ClientInteraction.objects.filter(
            created_at__lt=cutoff_date
        )

        # Завершені задачі старіші за рік
        old_completed_tasks = ClientTask.objects.filter(
            status='completed',
            completed_at__lt=cutoff_date
        )

        # Скасовані задачі
        cancelled_tasks = ClientTask.objects.filter(
            status='cancelled',
            created_at__lt=cutoff_date
        )

        self.stdout.write(f"📊 Знайдено для видалення:")
        self.stdout.write(f"   Взаємодії: {old_interactions.count()}")
        self.stdout.write(f"   Завершені задачі: {old_completed_tasks.count()}")
        self.stdout.write(f"   Скасовані задачі: {cancelled_tasks.count()}")

        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 Пробний запуск - нічого не видалено"))
            return

        # Підтвердження
        confirm = input("Продовжити видалення? (yes/no): ")
        if confirm.lower() != 'yes':
            self.stdout.write("❌ Скасовано")
            return

        # Видаляємо дані
        deleted_interactions = old_interactions.count()
        old_interactions.delete()

        deleted_completed = old_completed_tasks.count()
        old_completed_tasks.delete()

        deleted_cancelled = cancelled_tasks.count()
        cancelled_tasks.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Видалено:\n"
                f"   Взаємодії: {deleted_interactions}\n"
                f"   Завершені задачі: {deleted_completed}\n"
                f"   Скасовані задачі: {deleted_cancelled}"
            )
        )