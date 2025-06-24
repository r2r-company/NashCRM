from django.core.management.base import BaseCommand
from backend.services.cache_service import CacheService

class Command(BaseCommand):
    help = 'Управління кешем CRM системи'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['clear', 'stats', 'warmup'])

    def handle(self, *args, **options):
        action = options['action']

        if action == 'clear':
            CacheService.invalidate_all_reports()
            self.stdout.write("✅ Кеш очищено")

        elif action == 'stats':
            stats = CacheService.get_cache_stats()
            self.stdout.write(f"📊 Статистика кешу: {stats}")

        elif action == 'warmup':
            CacheService.warm_up_cache()
            self.stdout.write("🔥 Кеш прогрітий")