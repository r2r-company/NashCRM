import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime
from email.utils import parseaddr

from backend.models import Client, Lead, EmailIntegrationSettings
from backend.services.lead_creation_service import create_lead_with_logic
from backend.ws_notify import notify_lead_created


def normalize_phone(phone: str) -> str:
    """Нормалізує номер телефону до стандартного формату"""
    # Видаляємо всі символи крім цифр
    digits = re.sub(r'\D', '', phone)

    # Якщо номер починається з 0 (український формат)
    if digits.startswith("0"):
        digits = "38" + digits
    # Якщо номер 10 цифр без коду країни
    elif not digits.startswith("38") and len(digits) == 10:
        digits = "38" + digits

    return digits


def parse_email_body(msg) -> str:
    """Витягує текстовий контент з email повідомлення"""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
    return ""


def extract_lead_data(text: str) -> dict:
    """
    Парсить структуровані дані з email листа. Підтримує формати:
    - **form_id:** value (подвійні зірочки)
    - *form_id:* value (одинарні зірочки)
    - form_id: value (без зірочок)
    """

    def extract_field(label: str, text: str) -> str:
        """Витягує значення поля за його назвою"""
        # Формат з подвійними зірочками: **label:** value
        pattern = rf'\*\*{re.escape(label)}:\*\*\s*([^*]+?)(?=\*\*|$)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Формат з одинарними зірочками: *label:* value
        pattern = rf'\*{re.escape(label)}:\*\s*([^*\n]+?)(?=\*|$|\n)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Альтернативний формат без зірочок
        pattern = rf'{re.escape(label)}:\s*([^*\n]+?)(?=\n|\*\*|\*|$)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return ""

    # Обов'язкові поля для валідації ліда
    required_fields = ["form_id", "Lead Id", "Name", "Phone Number"]

    # Перевіряємо наявність всіх обов'язкових полів
    missing_fields = []
    for field in required_fields:
        if not extract_field(field, text):
            missing_fields.append(field)

    if missing_fields:
        print(f"❌ Відсутні обов'язкові поля: {', '.join(missing_fields)}")
        print(f"📄 Текст для аналізу:\n{text[:500]}...")  # Виводимо початок тексту для діагностики
        return None

    # Витягуємо основні дані
    lead_id = extract_field("Lead Id", text)
    form_id = extract_field("form_id", text) or extract_field("Form ID", text)
    name = extract_field("Name", text)
    phone_raw = extract_field("Phone Number", text)

    # Додаткові поля
    create_time = extract_field("Create Time", text)
    ad_id = extract_field("Ad Id", text)
    ad_name = extract_field("Ad Name", text)
    adgroup_id = extract_field("Adgroup Id", text)
    adgroup_name = extract_field("Adgroup Name", text)
    campaign_id = extract_field("Campaign Id", text)
    campaign_name = extract_field("Campaign Name", text)
    form_name = extract_field("Form Name", text)

    # Обробляємо телефон
    phone = normalize_phone(phone_raw) if phone_raw else ""
    if not phone:
        print(f"❌ Неможливо нормалізувати номер телефону: {phone_raw}")
        return None

    # Формуємо опис з усіх даних
    description_parts = [
        f"Lead ID: {lead_id}",
        f"Form ID: {form_id}",
        f"Create Time: {create_time}",
        f"Form Name: {form_name}",
        f"Campaign: {campaign_name} (ID: {campaign_id})",
        f"Ad Group: {adgroup_name} (ID: {adgroup_id})",
        f"Ad: {ad_name} (ID: {ad_id})",
        f"Original Phone: {phone_raw}",
        "--- Повний текст листа ---",
        text
    ]

    return {
        "full_name": name,
        "phone": phone,
        "email": "",  # В даному форматі email не передається
        "description": "\n".join(filter(None, description_parts)),
        "source": "email",
        "price": 0,
        "delivery_number": lead_id,  # Використовуємо Lead Id як номер доставки
    }


def fetch_emails_and_create_leads(start_date: datetime = None, settings_obj=None):
    """Завантажує email листи та створює ліди"""
    if not settings_obj:
        print("❌ Не передано settings_obj")
        return

    EMAIL_USER = settings_obj.email
    EMAIL_PASS = settings_obj.app_password
    IMAP_HOST = settings_obj.imap_host
    FOLDER = settings_obj.folder
    # Ігноруємо перевірку ключових слів - обробляємо всі листи
    # KEYWORDS = [k.strip().lower() for k in settings_obj.allowed_subject_keyword.split(",") if k.strip()]
    KEYWORDS = []  # Порожній список - не перевіряємо ключові слова

    print(f"📧 Налаштування:")
    print(f"   - Email: {EMAIL_USER}")
    print(f"   - IMAP: {IMAP_HOST}")
    print(f"   - Папка: {FOLDER}")
    print(f"   - Приймаємо листи від: ВСІХ відправників")
    print(f"   - Ключові слова в темі: {KEYWORDS if KEYWORDS else 'НЕ ПЕРЕВІРЯЄМО'}")

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select(FOLDER)

        if start_date is None:
            start_date = datetime.now()

        start_date_str = start_date.strftime("%d-%b-%Y")
        search_criteria = f'(SINCE "{start_date_str}")'
        status, messages = mail.search(None, search_criteria)

        if not messages[0]:
            print("📧 Нових листів не знайдено")
            return

        email_ids = messages[0].split()
        print(f"📬 Знайдено листів: {len(email_ids)}")

        processed_count = 0
        created_count = 0
        skipped_count = 0

        for num in email_ids:
            try:
                _, msg_data = mail.fetch(num, '(RFC822)')
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Отримуємо відправника
                from_raw = msg.get("From", "")
                from_email = parseaddr(from_raw)[1]

                # Отримуємо тему листа
                subject_raw, encoding = decode_header(msg["Subject"])[0]
                subject = subject_raw.decode(encoding or 'utf-8') if isinstance(subject_raw, bytes) else subject_raw

                print(f"\n📨 Обробляємо лист від: {from_email}")
                print(f"   Тема: {subject}")

                # НЕ ПЕРЕВІРЯЄМО ні відправника, ні ключові слова
                # Приймаємо ВСІ листи для обробки
                print(f"✅ Приймаємо лист для обробки")

                # Парсимо тіло листа
                body = parse_email_body(msg)
                print(f"📄 Тіло листа (перші 200 символів): {body[:200]}...")

                data = extract_lead_data(body)

                if not data:
                    print(f"⚠️ Лист не відповідає структурі ліда")
                    skipped_count += 1
                    continue

                processed_count += 1

                # Перевіряємо на дублікати по Lead ID
                if data.get("delivery_number"):
                    if Lead.objects.filter(delivery_number=data['delivery_number']).exists():
                        print(f"⚠️ Lead ID вже існує — {data['delivery_number']} — пропущено")
                        skipped_count += 1
                        continue

                # Логіка створення/оновлення клієнта
                phone = data['phone']
                name = data['full_name']

                try:
                    # Шукаємо існуючого клієнта по номеру
                    client = Client.objects.get(phone=phone)
                    print(f"📞 Знайдено існуючого клієнта: {client.full_name} ({phone})")

                    # Оновлюємо ім'я клієнта, якщо воно не заповнене або відрізняється
                    if not client.full_name or client.full_name != name:
                        old_name = client.full_name
                        client.full_name = name
                        client.save()
                        print(f"👤 Оновлено ім'я клієнта: '{old_name}' → '{name}'")

                    # Використовуємо існуючого менеджера клієнта
                    data['assigned_to'] = client.assigned_to

                except Client.DoesNotExist:
                    # Створюємо нового клієнта
                    client = Client.objects.create(
                        phone=phone,
                        full_name=name,
                        email=data.get('email', ''),
                        type='individual',
                        status='active'
                    )
                    print(f"👤 Створено нового клієнта: {name} ({phone})")
                    data['assigned_to'] = None

                # Створюємо лід
                lead, context = create_lead_with_logic(data)
                notify_lead_created(lead)
                created_count += 1

                print(f"✅ Лід створено: {lead.full_name} — {lead.phone} — Lead ID: {lead.delivery_number}")
                print(f"   Статус: {context['final_status']}, Менеджер: {context['assigned_to']}")

            except Exception as e:
                print(f"❌ Помилка обробки листа: {e}")
                import traceback
                traceback.print_exc()
                continue

        mail.logout()
        print(f"\n📊 Обробка завершена:")
        print(f"   - Всього листів знайдено: {len(email_ids)}")
        print(f"   - Листів оброблено: {processed_count}")
        print(f"   - Лідів створено: {created_count}")
        print(f"   - Листів пропущено: {skipped_count}")

    except Exception as e:
        print(f"❌ Помилка підключення до email: {e}")
        import traceback
        traceback.print_exc()


def fetch_all_emails_and_create_leads(start_date: datetime = None):
    """Обробляє всі налаштовані email акаунти"""
    for settings_obj in EmailIntegrationSettings.objects.all():
        print(f"\n{'=' * 60}")
        print(f"📧 Обробляємо акаунт: {settings_obj.name} ({settings_obj.email})")
        print(f"{'=' * 60}")
        fetch_emails_and_create_leads(start_date=start_date, settings_obj=settings_obj)