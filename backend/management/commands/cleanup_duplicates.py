# backend/management/commands/cleanup_duplicates.py
"""
Команда для очищення дублікатів клієнтів
Використання: python manage.py cleanup_duplicates
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from backend.models import Client


class Command(BaseCommand):
    help = 'Очищення дублікатів клієнтів'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Тільки показати дублікати, не видаляти',
        )

    def handle(self, *args, **options):
        self.stdout.write("🧹 ОЧИЩЕННЯ ДУБЛІКАТІВ КЛІЄНТІВ")
        self.stdout.write("=" * 40)

        # Знаходимо дублікати
        duplicate_clients = Client.objects.values('phone').annotate(
            count=Count('id')
        ).filter(count__gt=1).order_by('-count')

        if not duplicate_clients:
            self.stdout.write("✅ Дублікатів не знайдено!")
            return

        total_duplicates = 0
        for dup in duplicate_clients:
            phone = dup['phone']
            count = dup['count']

            self.stdout.write(f"\n📞 Номер: {phone} ({count} дублікатів)")

            # Отримуємо всіх клієнтів з цим номером
            clients = Client.objects.filter(phone=phone).order_by('created_at')

            # Залишаємо першого (найстаршого), видаляємо решту
            keeper = clients.first()
            duplicates_to_delete = clients.exclude(id=keeper.id)

            self.stdout.write(f"   ✅ Залишаємо: #{keeper.id} - {keeper.full_name} (створено: {keeper.created_at})")

            for duplicate in duplicates_to_delete:
                if options['dry_run']:
                    self.stdout.write(f"   🗑️ [DRY RUN] Видалили б: #{duplicate.id} - {duplicate.full_name}")
                else:
                    self.stdout.write(f"   🗑️ Видаляємо: #{duplicate.id} - {duplicate.full_name}")
                    duplicate.delete()
                total_duplicates += 1

        if options['dry_run']:
            self.stdout.write(f"\n📊 [DRY RUN] Знайдено {total_duplicates} дублікатів для видалення")
            self.stdout.write("Запустіть без --dry-run для фактичного видалення")
        else:
            self.stdout.write(f"\n✅ Видалено {total_duplicates} дублікатів")

        self.stdout.write("\n🔍 ПОТОЧНА СТАТИСТИКА:")
        total_clients = Client.objects.count()
        unique_phones = Client.objects.values('phone').distinct().count()
        self.stdout.write(f"   👥 Всього клієнтів: {total_clients}")
        self.stdout.write(f"   📞 Унікальних номерів: {unique_phones}")

        if total_clients != unique_phones:
            self.stdout.write("⚠️ Все ще є дублікати! Запустіть команду знову.")
        else:
            self.stdout.write("✅ Дублікатів немає!")