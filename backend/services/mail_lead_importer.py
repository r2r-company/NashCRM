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
    digits = re.sub(r'\D', '', phone)
    if digits.startswith("0"):
        digits = "38" + digits
    elif not digits.startswith("38") and len(digits) == 10:
        digits = "38" + digits
    return digits


def parse_email_body(msg) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
    return ""


def extract_lead_data(text: str) -> dict:
    phone_match = re.search(r"\+?\d{10,15}", text)
    raw_phone = phone_match.group(0) if phone_match else "0000000000"
    phone = normalize_phone(raw_phone)

    email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
    email_val = email_match.group(0) if email_match else ""

    name_match = re.search(r"Ім.?я\s*[:\-]?\s*(.+)", text)
    name_val = name_match.group(1).strip() if name_match else ""

    # Парсимо Delivery number
    delivery_match = re.search(r"Delivery number\s*[:\-]?\s*(\S+)", text, re.IGNORECASE)
    delivery_number = delivery_match.group(1).strip() if delivery_match else ""

    return {
        "full_name": name_val,
        "phone": phone,
        "email": email_val,
        "description": text,
        "source": "email",
        "price": 0,
        "delivery_number": delivery_number,
    }


def fetch_emails_and_create_leads(start_date: datetime = None, account_name: str = "default"):
    try:
        settings = EmailIntegrationSettings.objects.get(name=account_name)
    except EmailIntegrationSettings.DoesNotExist:
        print(f"❌ Налаштування '{account_name}' не знайдено")
        return

    EMAIL_USER = settings.email
    EMAIL_PASS = settings.app_password
    IMAP_HOST = settings.imap_host
    FOLDER = settings.folder
    ALLOWED_SENDER = settings.allowed_sender.lower()
    ALLOWED_SUBJECT = settings.allowed_subject_keyword.lower()

    mail = imaplib.IMAP4_SSL(IMAP_HOST)
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select(FOLDER)

    if start_date is None:
        start_date = datetime.now()

    start_date_str = start_date.strftime("%d-%b-%Y")
    search_criteria = f'(SINCE "{start_date_str}")'
    status, messages = mail.search(None, search_criteria)

    for num in messages[0].split():
        _, msg_data = mail.fetch(num, '(RFC822)')
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        from_raw = msg.get("From", "")
        from_email = parseaddr(from_raw)[1]

        subject_raw, encoding = decode_header(msg["Subject"])[0]
        subject = subject_raw.decode(encoding or 'utf-8') if isinstance(subject_raw, bytes) else subject_raw

        if not (
                from_email.lower() == ALLOWED_SENDER
                or ALLOWED_SUBJECT in subject.lower()
        ):
            print(f"⛔ Пропущено: {from_email} — {subject}")
            continue

        body = parse_email_body(msg)
        if "Delivery number:" not in body:
            print(f"⛔ Нема Delivery number — пропущено: {from_email} — {subject}")
            continue

        data = extract_lead_data(body)

        # 🛡 Перевірка дубля: delivery_number завжди має бути унікальний
        if data.get("delivery_number"):
            if Lead.objects.filter(delivery_number=data['delivery_number']).exists():
                print(f"⚠️ Delivery number вже існує — {data['delivery_number']} — пропущено")
                continue
        else:
            # fallback перевірка по телефону + частині опису, як було
            duplicate = Lead.objects.filter(
                status__in=['new', 'queued', 'in_work']
            ).filter(
                phone=data['phone'],
                description__icontains=data['description'][:50]
            )
            if duplicate.exists():
                print(f"⚠️ Дублікат ліда по телефону — {data['phone']} — пропущено")
                continue

        # 🧠 Клієнт
        try:
            client = Client.objects.get(phone=data['phone'])
            data['full_name'] = client.full_name or "Без імені"
            data['assigned_to'] = client.assigned_to
        except Client.DoesNotExist:
            client = Client.objects.create(
                phone=data['phone'],
                full_name=data['full_name'] or "Без імені",
                email=data['email']
            )
            data['full_name'] = client.full_name
            data['assigned_to'] = None

        # ✅ Створення
        lead, context = create_lead_with_logic(data)
        print(f"📣 Сповіщення WebSocket для менеджера: {lead.assigned_to_id}")
        notify_lead_created(lead)
        print(f"[✔] Лід створено: {lead.full_name} — {lead.phone} — {lead.delivery_number}")

    mail.logout()
