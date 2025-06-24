# backend/apps.py - ОНОВЛЕНА ВЕРСІЯ з сигналами
import os
import threading
from django.apps import AppConfig
from django.core.management import call_command


class BackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backend'

    def ready(self):
        # 🚀 ІМПОРТУЄМО СИГНАЛИ ПЕРШИМ ДЕЛОМ
        try:
            from . import signals
            print("📡 Django signals успішно зареєстровано!")
        except ImportError as e:
            print(f"❌ Помилка імпорту сигналів: {e}")
        except Exception as e:
            print(f"⚠️ Інша помилка при імпорті сигналів: {e}")

        # Email інтеграція тільки для основного процесу
        if os.environ.get('RUN_MAIN') == 'true':  # щоб не запускалось двічі
            def run_fetch():
                try:
                    call_command('fetch_leads_from_email', '--loop')
                except Exception as e:
                    print(f"❌ Помилка email інтеграції: {e}")

            thread = threading.Thread(target=run_fetch)
            thread.daemon = True
            thread.start()
            print("📧 Email інтеграція запущена")

        print("🚀 Backend ERP/CRM успішно ініціалізовано")