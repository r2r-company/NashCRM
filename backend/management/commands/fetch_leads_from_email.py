from django.core.management.base import BaseCommand
from backend.services.mail_lead_importer import fetch_emails_and_create_leads
from backend.models import EmailIntegrationSettings  # або звідки в тебе ця модель
from datetime import datetime, date
import time

class Command(BaseCommand):
    help = "Імпортує ліди з пошти через IMAP (по колу)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--since',
            type=str,
            help='Дата з якої починати парсити (у форматі YYYY-MM-DD)'
        )
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Запускати в нескінченному циклі'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=None,
            help='Інтервал між запусками (сек). Якщо не вказано — береться з моделі EmailIntegrationSettings'
        )

    def handle(self, *args, **options):
        since = options.get("since") or date.today().strftime("%Y-%m-%d")
        loop = options.get("loop")
        cli_interval = options.get("interval")

        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                self.stderr.write("❌ Невірний формат дати. Має бути: YYYY-MM-DD")
                return
        else:
            since_date = datetime.now()

        try:
            settings = EmailIntegrationSettings.objects.get(name="default")
            interval = cli_interval if cli_interval is not None else settings.check_interval
        except EmailIntegrationSettings.DoesNotExist:
            interval = cli_interval if cli_interval is not None else 30
            self.stderr.write("⚠️ EmailIntegrationSettings з name='default' не знайдено. Використовую інтервал по замовчуванню.")

        def fetch():
            self.stdout.write(f"📥 Парсимо пошту з {since_date.strftime('%Y-%m-%d')}...")
            try:
                fetch_emails_and_create_leads(start_date=since_date, settings_obj=settings)
                self.stdout.write(self.style.SUCCESS("✅ Ліди з пошти створено!"))
            except Exception as e:
                self.stderr.write(f"❌ Помилка: {str(e)}")

        if loop:
            while True:
                fetch()
                time.sleep(interval)
        else:
            fetch()
