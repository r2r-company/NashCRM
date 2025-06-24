# backend/services/mail_lead_importer.py - ПОКРАЩЕНА ВЕРСІЯ

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
    digits = re.sub(r'\D', '', phone)
    if digits.startswith("0"):
        digits = "38" + digits
    elif not digits.startswith("38") and len(digits) == 10:
        digits = "38" + digits
    return digits


def parse_email_body(msg) -> str:
    """Витягує текстовий контент з email повідомлення"""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
    return ""


def is_lead_email(text: str, subject: str = "", sender: str = "") -> bool:
    """
    🔍 РОЗУМНА ПЕРЕВІРКА - чи є email справжнім лідом
    """

    # 1. Перевіряємо наявність ключових слів лідів в темі
    lead_subject_keywords = [
        'new lead', 'form submission', 'contact form', 'заявка', 'форма',
        'lead id', 'form id', 'заявление', 'запрос', 'inquiry'
    ]

    subject_lower = subject.lower()
    for keyword in lead_subject_keywords:
        if keyword in subject_lower:
            print(f"✅ Знайдено ключове слово в темі: '{keyword}'")
            return True

    # 2. Перевіряємо структуру ліда в тексті
    lead_patterns = [
        r'\*\*form_id:\*\*',  # **form_id:**
        r'\*form_id:\*',  # *form_id:*
        r'form_id\s*:',  # form_id:
        r'\*\*Lead Id:\*\*',  # **Lead Id:**
        r'Lead Id\s*:',  # Lead Id:
        r'\*\*Name:\*\*',  # **Name:**
        r'Name\s*:',  # Name:
        r'\*\*Phone Number:\*\*',  # **Phone Number:**
        r'Phone Number\s*:',  # Phone Number:
    ]

    pattern_matches = 0
    for pattern in lead_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            pattern_matches += 1

    # Якщо знайдено 3+ патернів - це лід
    if pattern_matches >= 3:
        print(f"✅ Знайдено {pattern_matches} патернів ліда")
        return True

    # 3. Перевіряємо виключення - маркетингові листи
    marketing_keywords = [
        'unsubscribe', 'відписатися', 'premium video', 'newsletter',
        'Elliott Wave', 'investment', 'trading', 'market analysis',
        'promotional', 'discount', 'sale', 'offer expires'
    ]

    text_lower = text.lower()
    marketing_found = []
    for keyword in marketing_keywords:
        if keyword.lower() in text_lower:
            marketing_found.append(keyword)

    if marketing_found:
        print(f"❌ Виявлено маркетинговий контент: {marketing_found}")
        return False

    # 4. Перевіряємо відправника
    suspicious_senders = [
        'noreply', 'no-reply', 'newsletter', 'marketing', 'promo',
        'elliottwave', 'notifications', 'updates'
    ]

    sender_lower = sender.lower()
    for suspicious in suspicious_senders:
        if suspicious in sender_lower:
            print(f"❌ Підозрілий відправник: '{suspicious}' в '{sender}'")
            return False

    print(f"⚠️ Невизначений тип email - не схоже на лід")
    return False


def extract_lead_data(text: str) -> dict:
    """
    Парсить структуровані дані з email листа лише якщо це справжній лід
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
        "email": "",
        "description": "\n".join(filter(None, description_parts)),
        "source": "email",
        "price": 0,
        "delivery_number": lead_id,
        "order_number": form_id
    }


def fetch_emails_and_create_leads(start_date: datetime = None, settings_obj=None):
    """Завантажує email листи та створює ліди з розумною фільтрацією"""
    if not settings_obj:
        print("❌ Не передано settings_obj")
        return

    EMAIL_USER = settings_obj.email
    EMAIL_PASS = settings_obj.app_password
    IMAP_HOST = settings_obj.imap_host
    FOLDER = settings_obj.folder

    print(f"📧 Налаштування:")
    print(f"   - Email: {EMAIL_USER}")
    print(f"   - IMAP: {IMAP_HOST}")
    print(f"   - Папка: {FOLDER}")
    print(f"   - Розумна фільтрація: ✅ УВІМКНЕНА")

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
        filtered_count = 0  # Нова метрика - відфільтровані

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

                print(f"\n📨 Обробляємо лист:")
                print(f"   Від: {from_email}")
                print(f"   Тема: {subject}")

                # Парсимо тіло листа
                body = parse_email_body(msg)

                # 🔍 РОЗУМНА ПЕРЕВІРКА - чи є це лідом?
                if not is_lead_email(body, subject, from_email):
                    print(f"🚫 Email не є лідом - пропускаємо")
                    filtered_count += 1
                    continue

                print(f"✅ Email розпізнано як лід - обробляємо")

                data = extract_lead_data(body)

                if not data:
                    print(f"⚠️ Лист є лідом, але структура даних невірна")
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
                    client = Client.objects.get(phone=phone)
                    print(f"📞 Знайдено існуючого клієнта: {client.full_name} ({phone})")

                    # Оновлюємо ім'я клієнта, якщо воно не заповнене або відрізняється
                    if not client.full_name or client.full_name != name:
                        old_name = client.full_name
                        client.full_name = name
                        client.save()
                        print(f"👤 Оновлено ім'я клієнта: '{old_name}' → '{name}'")

                    data['assigned_to'] = client.assigned_to

                except Client.DoesNotExist:
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
        print(f"   - 🚫 Відфільтровано (не ліди): {filtered_count}")
        print(f"   - 📋 Листів оброблено як ліди: {processed_count}")
        print(f"   - ✅ Лідів створено: {created_count}")
        print(f"   - ⚠️ Пропущено (дублікати/помилки): {skipped_count}")

    except Exception as e:
        print(f"❌ Помилка підключення до email: {e}")
        import traceback
        traceback.print_exc()


def fetch_all_emails_and_create_leads(start_date: datetime = None):
    """Обробляє всі налаштовані email акаунти з розумною фільтрацією"""
    for settings_obj in EmailIntegrationSettings.objects.all():
        print(f"\n{'=' * 60}")
        print(f"📧 Обробляємо акаунт: {settings_obj.name} ({settings_obj.email})")
        print(f"{'=' * 60}")
        fetch_emails_and_create_leads(start_date=start_date, settings_obj=settings_obj)


# 🔧 ТЕСТОВА ФУНКЦІЯ ДЛЯ ПЕРЕВІРКИ ФІЛЬТРАЦІЇ
def test_email_filter():
    """Тестує роботу фільтра email"""

    # Тест 1: Справжній лід
    lead_text = """
    **form_id:** 12345
    **Lead Id:** LEAD_67890
    **Name:** Іван Петренко
    **Phone Number:** +38067123456
    **Create Time:** 2024-06-25 10:30:00
    """

    result1 = is_lead_email(lead_text, "New Lead Submission", "forms@company.com")
    print(f"Тест 1 (справжній лід): {'✅ ПРОЙШОВ' if result1 else '❌ НЕ ПРОЙШОВ'}")

    # Тест 2: Маркетинговий лист
    marketing_text = """
    We've unlocked a premium video for you for a limited time…
    Hi Elliott Waver,
    Most investors would say that oil prices are governed by supply and demand.
    Unsubscribe from future emails.
    """

    result2 = is_lead_email(marketing_text, "Premium Video Unlocked", "noreply@elliottwave.com")
    print(f"Тест 2 (маркетинг): {'✅ ПРОЙШОВ' if not result2 else '❌ НЕ ПРОЙШОВ'}")

    return result1 and not result2


if __name__ == "__main__":
    test_email_filter()