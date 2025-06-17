import os
import threading

from django.apps import AppConfig
from django.core.management import call_command


class BackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backend'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':  # щоб не запускалось двічі
            def run_fetch():
                call_command('fetch_leads_from_email', '--loop')

            thread = threading.Thread(target=run_fetch)
            thread.daemon = True
            thread.start()