# backend/management/commands/update_client_metrics.py
"""
Команда для масового оновлення метрик клієнтів
Використання: python manage.py update_client_metrics
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from backend.models import Client
import time


class Command(BaseCommand):
    help = 'Оновлює метрики всіх клієнтів (температуру, АКБ сегмент, RFM)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Кількість клієнтів для обробки за раз (за замовчуванням: 100)'
        )
        parser.add_argument(
            '--only-akb',
            action='store_true',
            help='Оновлювати тільки клієнтів з покупками (АКБ)'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        only_akb = options['only_akb']

        start_time = time.time()

        # Вибираємо клієнтів для оновлення
        if only_akb:
            clients = Client.objects.filter(total_orders__gt=0)
            self.stdout.write(f"🎯 Оновлюємо тільки АКБ клієнтів...")
        else:
            clients = Client.objects.all()
            self.stdout.write(f"🎯 Оновлюємо всіх клієнтів...")

        total_count = clients.count()
        self.stdout.write(f"📊 Знайдено клієнтів: {total_count}")

        updated_count = 0
        errors_count = 0

        # Обробляємо батчами
        for i in range(0, total_count, batch_size):
            batch = clients[i:i + batch_size]

            for client in batch:
                try:
                    old_temperature = client.temperature
                    old_segment = client.akb_segment

                    client.update_client_metrics()

                    # Логуємо важливі зміни
                    if client.temperature != old_temperature:
                        self.stdout.write(
                            f"🌡️ {client.full_name}: {old_temperature} → {client.temperature}"
                        )

                    if client.akb_segment != old_segment:
                        self.stdout.write(
                            f"💰 {client.full_name}: {old_segment} → {client.akb_segment}"
                        )

                    updated_count += 1

                except Exception as e:
                    errors_count += 1
                    self.stderr.write(f"❌ Помилка для клієнта {client.id}: {str(e)}")

            # Показуємо прогрес
            progress = ((i + batch_size) / total_count) * 100
            self.stdout.write(f"⏳ Прогрес: {min(progress, 100):.1f}% ({updated_count}/{total_count})")

        # Підсумок
        elapsed_time = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Завершено!\n"
                f"   Оновлено: {updated_count} клієнтів\n"
                f"   Помилок: {errors_count}\n"
                f"   Час виконання: {elapsed_time:.2f} секунд"
            )
        )