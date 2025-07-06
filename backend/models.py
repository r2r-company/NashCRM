import os
import re
from datetime import timedelta, datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum

from django.utils.timezone import now

def lead_file_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{now().strftime('%Y%m%d%H%M%S%f')}.{ext}"
    return os.path.join("lead_files", filename)




class CustomUser(models.Model):
    INTERFACE_CHOICES = [
        ('admin', 'Адміністратор'),
        ('accountant', 'Бухгалтер'),
        ('manager', 'Менеджер'),
        ('warehouse', 'Складський'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Користувач")
    interface_type = models.CharField(max_length=20, choices=INTERFACE_CHOICES, verbose_name="Тип інтерфейсу")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True, verbose_name="Фото")

    def __str__(self):
        return f"{self.user.username} ({self.get_interface_type_display()})"

    class Meta:
        verbose_name = "Користувач інтерфейсу"
        verbose_name_plural = "Користувачі інтерфейсу"
        indexes = [
            models.Index(fields=['interface_type']),
            models.Index(fields=['user', 'interface_type']),
        ]
class LeadFile(models.Model):
    lead = models.ForeignKey("Lead", related_name="uploaded_files", on_delete=models.CASCADE)
    file = models.FileField(upload_to=lead_file_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)  # тільки це поле

    class Meta:
        verbose_name = "Файл ліда"
        verbose_name_plural = "Файли лідів"

    def __str__(self):
        return f"{self.lead.full_name} – {self.file.name}"



class Lead(models.Model):
    STATUS_CHOICES = [
        ('queued', 'У черзі'),
        ('in_work', 'Обробляється менеджером'),
        ('awaiting_prepayment', 'Очікую аванс'),
        ('preparation', 'В роботу'),
        ('warehouse_processing', 'Обробка на складі'),
        ('warehouse_ready', 'Склад - готовий до відгрузки'),  # 🆕 НОВИЙ СТАТУС
        ('on_the_way', 'В дорозі'),
        ('completed', 'Завершено'),
        ('declined', 'Відмовлено'),
    ]

    full_name = models.CharField(max_length=255, verbose_name="ПІБ")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    source = models.CharField(max_length=100, blank=True, verbose_name="Джерело")
    description = models.TextField(blank=True, verbose_name="Опис")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Ціна")
    advance = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Аванс")
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Вартість доставки")
    comment = models.TextField(blank=True, null=True, verbose_name="Коментар")
    order_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="Номер замовлення")

    delivery_number = models.CharField(max_length=100, blank=True, verbose_name="ТТН")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='queued', verbose_name="Статус")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Призначено")
    queued_position = models.PositiveIntegerField(null=True, blank=True, verbose_name="Позиція в черзі")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Створено")
    status_updated_at = models.DateTimeField(null=True, blank=True)
    actual_cash = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    full_address = models.CharField("Адреса (Google)", max_length=512, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    street = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.full_name} — {self.price} грн ({self.get_status_display()})"

    @property
    def manager_reward(self):
        return round(self.price * 0.03, 2) if self.price else 0

    @property
    def remaining_amount(self):
        return (self.price or 0) - (self.advance or 0)

    @property
    def is_two_weeks_old(self):
        return self.status != 'completed' and self.created_at <= now() - timedelta(days=14)

    @property
    def is_three_months_old(self):
        return self.status != 'completed' and self.created_at <= now() - timedelta(days=90)

    class Meta:
        verbose_name = "Лід"
        verbose_name_plural = "Ліди"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status_updated_at']),
            models.Index(fields=['phone']),
            models.Index(fields=['assigned_to']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['phone', 'status']),
            models.Index(fields=['created_at', 'assigned_to']),
            models.Index(fields=['status', 'price']),
        ]


class Client(models.Model):
    CLIENT_TYPE_CHOICES = [
        ('individual', 'Фізична особа'),
        ('company', 'Компанія'),
        ('vip', 'VIP-клієнт'),
    ]

    STATUS_CHOICES = [
        ('active', 'Активний'),
        ('inactive', 'Неактивний'),
        ('blacklist', 'У чорному списку'),
    ]

    # 🔥 НОВА КЛАСИФІКАЦІЯ ПО ТЕМПЕРАТУРІ
    TEMPERATURE_CHOICES = [
        ('cold', 'Холодний лід'),  # Новий контакт, не проявляв інтерес
        ('warm', 'Теплий лід'),  # Проявляв інтерес, але не купував
        ('hot', 'Гарячий лід'),  # Готовий до покупки зараз
        ('customer', 'Клієнт АКБ'),  # Здійснив покупку
        ('loyal', 'Лояльний клієнт'),  # Постійний клієнт
        ('sleeping', 'Сплячий клієнт')  # Давно не купував
    ]

    # 🔥 КЛАСИФІКАЦІЯ АКБ (АКТИВНА КЛІЄНТСЬКА БАЗА)
    AKB_SEGMENT_CHOICES = [
        ('vip', 'VIP (>50к грн)'),
        ('premium', 'Преміум (20-50к грн)'),
        ('standard', 'Стандарт (5-20к грн)'),
        ('basic', 'Базовий (<5к грн)'),
        ('new', 'Новий клієнт'),
        ('inactive', 'Неактивний'),
    ]

    # Основні поля
    full_name = models.CharField(max_length=255, verbose_name="ПІБ")
    phone = models.CharField(max_length=30, unique=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    company_name = models.CharField(max_length=255, blank=True, verbose_name="Назва компанії")
    type = models.CharField(max_length=20, choices=CLIENT_TYPE_CHOICES, default='individual', verbose_name="Тип")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Статус")

    # 🔥 НОВІ ПОЛЯ CRM
    temperature = models.CharField(max_length=20, choices=TEMPERATURE_CHOICES, default='cold',
                                   verbose_name="Температура ліда")
    akb_segment = models.CharField(max_length=20, choices=AKB_SEGMENT_CHOICES, default='new',
                                   verbose_name="Сегмент АКБ")

    # Фінансові показники
    total_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Загальна сума покупок")
    avg_check = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Середній чек")
    total_orders = models.PositiveIntegerField(default=0, verbose_name="Кількість замовлень")

    # Дати активності
    first_purchase_date = models.DateTimeField(null=True, blank=True, verbose_name="Перша покупка")
    last_purchase_date = models.DateTimeField(null=True, blank=True, verbose_name="Остання покупка")
    last_contact_date = models.DateTimeField(null=True, blank=True, verbose_name="Останній контакт")

    # CRM поля
    notes = models.TextField(blank=True, verbose_name="Нотатки")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Менеджер")
    difficulty_rating = models.PositiveSmallIntegerField(
        default=1,
        choices=[(i, f"{i} зірок") for i in range(1, 6)],
        verbose_name="Рейтинг складності"
    )

    # 🔥 НОВІ CRM ПОЛЯ
    lead_source = models.CharField(max_length=100, blank=True, verbose_name="Джерело першого ліда")
    preferred_contact_method = models.CharField(max_length=50, choices=[
        ('phone', 'Телефон'),
        ('email', 'Email'),
        ('messenger', 'Месенджер'),
        ('sms', 'SMS'),
    ], default='phone', verbose_name="Спосіб зв'язку")

    # Геолокація
    country = models.CharField(max_length=100, blank=True, verbose_name="Країна")
    city = models.CharField(max_length=100, blank=True, verbose_name="Місто")

    # RFM аналіз (автоматично розраховується)
    rfm_recency = models.PositiveIntegerField(null=True, blank=True, verbose_name="R - Recency (дні)")
    rfm_frequency = models.PositiveIntegerField(null=True, blank=True, verbose_name="F - Frequency (покупок)")
    rfm_monetary = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
                                       verbose_name="M - Monetary (сума)")
    rfm_score = models.CharField(max_length=10, blank=True, verbose_name="RFM Score (111-555)")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Створено")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Оновлено")

    def save(self, *args, **kwargs):
        self.phone = self.normalize_phone(self.phone)
        super().save(*args, **kwargs)
        # Після збереження автоматично оновлюємо метрики
        self.update_client_metrics()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if digits.startswith("0"):
            digits = "38" + digits
        elif not digits.startswith("38") and len(digits) == 10:
            digits = "38" + digits
        return digits

    def update_client_metrics(self):
        """🔥 АВТОМАТИЧНЕ ОНОВЛЕННЯ ВСІХ МЕТРИК КЛІЄНТА"""


        # Рахуємо статистику по завершених лідах
        completed_leads = Lead.objects.filter(
            phone=self.phone,
            status='completed'
        )

        # Фінансові метрики
        payments = LeadPaymentOperation.objects.filter(
            lead__phone=self.phone,
            operation_type='received'
        )

        total_spent = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        total_orders = completed_leads.count()
        avg_check = total_spent / total_orders if total_orders > 0 else Decimal('0')

        # Дати
        first_purchase = completed_leads.order_by('created_at').first()
        last_purchase = completed_leads.order_by('-created_at').first()

        # Оновлюємо поля
        self.total_spent = total_spent
        self.total_orders = total_orders
        self.avg_check = avg_check
        self.first_purchase_date = first_purchase.created_at if first_purchase else None
        self.last_purchase_date = last_purchase.created_at if last_purchase else None

        # Автоматично визначаємо температуру
        self.temperature = self.calculate_temperature()

        # Автоматично визначаємо сегмент АКБ
        self.akb_segment = self.calculate_akb_segment()

        # RFM аналіз
        self.calculate_rfm_metrics()

        # Зберігаємо без викликання save() щоб уникнути рекурсії
        Client.objects.filter(id=self.id).update(
            total_spent=self.total_spent,
            total_orders=self.total_orders,
            avg_check=self.avg_check,
            first_purchase_date=self.first_purchase_date,
            last_purchase_date=self.last_purchase_date,
            temperature=self.temperature,
            akb_segment=self.akb_segment,
            rfm_recency=self.rfm_recency,
            rfm_frequency=self.rfm_frequency,
            rfm_monetary=self.rfm_monetary,
            rfm_score=self.rfm_score,
        )

    def calculate_temperature(self) -> str:
        """🌡️ АВТОМАТИЧНЕ ВИЗНАЧЕННЯ ТЕМПЕРАТУРИ ЛІДА"""
        if self.total_orders == 0:
            # Перевіряємо чи були спроби контакту
            leads_count = Lead.objects.filter(phone=self.phone).count()
            if leads_count == 0:
                return 'cold'  # Новий контакт
            elif leads_count == 1:
                return 'warm'  # Один лід, але не купував
            else:
                return 'hot'  # Багато лідів, але не купував - гарячий

        # Клієнти що купували
        days_since_last_purchase = None
        if self.last_purchase_date:
            days_since_last_purchase = (now() - self.last_purchase_date).days

        if self.total_orders >= 3:
            return 'loyal'  # Лояльний клієнт (3+ покупки)
        elif days_since_last_purchase and days_since_last_purchase > 180:
            return 'sleeping'  # Сплячий клієнт (>6 місяців)
        else:
            return 'customer'  # Активний клієнт АКБ

    def calculate_akb_segment(self) -> str:
        """💰 АВТОМАТИЧНЕ ВИЗНАЧЕННЯ СЕГМЕНТА АКБ"""
        if self.total_orders == 0:
            return 'new'

        if self.total_spent >= 50000:
            return 'vip'
        elif self.total_spent >= 20000:
            return 'premium'
        elif self.total_spent >= 5000:
            return 'standard'
        elif self.total_spent > 0:
            return 'basic'
        else:
            return 'inactive'

    def calculate_rfm_metrics(self):
        """📊 RFM АНАЛІЗ (Recency, Frequency, Monetary)"""
        if self.last_purchase_date:
            self.rfm_recency = (now() - self.last_purchase_date).days
        else:
            self.rfm_recency = 999  # Ніколи не купував

        self.rfm_frequency = self.total_orders
        self.rfm_monetary = self.total_spent

        # Розраховуємо RFM скор (1-5 для кожного параметра)
        r_score = self.get_rfm_recency_score()
        f_score = self.get_rfm_frequency_score()
        m_score = self.get_rfm_monetary_score()

        self.rfm_score = f"{r_score}{f_score}{m_score}"

    def get_rfm_recency_score(self) -> int:
        """R - Recency: чим менше днів, тим краще"""
        if self.rfm_recency <= 30:
            return 5  # Купував останній місяць
        elif self.rfm_recency <= 90:
            return 4  # Останні 3 місяці
        elif self.rfm_recency <= 180:
            return 3  # Останні 6 місяців
        elif self.rfm_recency <= 365:
            return 2  # Останній рік
        else:
            return 1  # Більше року або ніколи

    def get_rfm_frequency_score(self) -> int:
        """F - Frequency: кількість покупок"""
        if self.rfm_frequency >= 10:
            return 5
        elif self.rfm_frequency >= 5:
            return 4
        elif self.rfm_frequency >= 3:
            return 3
        elif self.rfm_frequency >= 2:
            return 2
        else:
            return 1

    def get_rfm_monetary_score(self) -> int:
        """M - Monetary: сума покупок"""
        if self.rfm_monetary >= 50000:
            return 5
        elif self.rfm_monetary >= 20000:
            return 4
        elif self.rfm_monetary >= 10000:
            return 3
        elif self.rfm_monetary >= 5000:
            return 2
        else:
            return 1

    @property
    def is_akb(self) -> bool:
        """Чи є клієнт частиною активної клієнтської бази"""
        return self.total_orders > 0 and self.akb_segment != 'inactive'

    @property
    def customer_lifetime_value(self) -> Decimal:
        """LTV - прогнозована життєва вартість клієнта"""
        if self.total_orders == 0:
            return Decimal('0')

        # Проста формула: середній чек * прогнозована кількість покупок
        avg_purchase_interval_days = 90  # Припускаємо покупку раз в 3 місяці
        estimated_lifetime_years = 3  # Припускаємо 3 роки співпраці
        estimated_purchases = int((estimated_lifetime_years * 365) / avg_purchase_interval_days)

        return self.avg_check * estimated_purchases

    @property
    def risk_of_churn(self) -> str:
        """Ризик відтоку клієнта"""
        if self.temperature == 'sleeping':
            return 'Високий'
        elif self.rfm_recency is not None and self.rfm_recency > 180:
            return 'Середній'
        elif self.rfm_score and self.rfm_score.startswith('5'):
            return 'Низький'
        return 'Середній'

    @property
    def next_contact_recommendation(self) -> str:
        """Рекомендації для наступного контакту"""
        if self.temperature == 'cold':
            return 'Розігрівання: презентація продукту'
        elif self.temperature == 'warm':
            return 'Персональна пропозиція'
        elif self.temperature == 'hot':
            return 'ТЕРМІНОВО: готовий до покупки!'
        elif self.temperature == 'sleeping':
            return 'Реактивація: спеціальна знижка'
        elif self.temperature == 'loyal':
            return 'Програма лояльності, VIP-пропозиції'
        else:
            return 'Підтримка відносин'

    def __str__(self):
        return f"{self.full_name} ({self.phone}) - {self.get_temperature_display()}"

    class Meta:
        verbose_name = "Клієнт"
        verbose_name_plural = "Клієнти"
        indexes = [
            # Існуючі індекси
            models.Index(fields=['phone']),
            models.Index(fields=['status']),
            models.Index(fields=['assigned_to']),
            models.Index(fields=['created_at']),
            models.Index(fields=['type', 'status']),

            # 🔥 НОВІ ІНДЕКСИ ДЛЯ CRM
            models.Index(fields=['temperature']),
            models.Index(fields=['akb_segment']),
            models.Index(fields=['total_spent']),
            models.Index(fields=['last_purchase_date']),
            models.Index(fields=['temperature', 'akb_segment']),
            models.Index(fields=['assigned_to', 'temperature']),
            models.Index(fields=['akb_segment', 'total_spent']),
            models.Index(fields=['rfm_score']),
        ]


class LeadPaymentOperation(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="payment_operations", verbose_name="Лід")
    operation_type = models.CharField(max_length=20, choices=[
        ('expected', 'Очікувана сума'),
        ('received', 'Отримано від водія'),
    ], verbose_name="Тип операції")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сума")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата створення")
    comment = models.CharField(max_length=255, blank=True, verbose_name="Коментар")

    def __str__(self):
        return f"{self.lead.full_name} – {self.get_operation_type_display()} – {self.amount} грн"

    class Meta:
        verbose_name = "Фінансова операція по ліду"
        verbose_name_plural = "Фінансові операції по лідах"
        # 🚀 КРИТИЧНІ ІНДЕКСИ для фінансових звітів
        indexes = [
            # Для фільтрації по типу операції (найчастіше використовується)
            models.Index(fields=['operation_type']),

            # Для зв'язку з лідом
            models.Index(fields=['lead']),

            # Для звітів по датах
            models.Index(fields=['created_at']),

            # Композитні індекси для агрегацій
            models.Index(fields=['lead', 'operation_type']),  # Сума по ліду
            models.Index(fields=['operation_type', 'amount']),  # Фінансові підсумки
            models.Index(fields=['created_at', 'operation_type']),  # Звіти по датах
            models.Index(fields=['lead', 'created_at']),  # Хронологія оплат ліда
        ]


class EmailIntegrationSettings(models.Model):
    name = models.CharField(max_length=100, unique=True, default="default", verbose_name="Назва акаунта")
    email = models.EmailField(verbose_name="Email логіну")
    app_password = models.CharField(max_length=100, verbose_name="App Password")
    imap_host = models.CharField(max_length=100, default="imap.gmail.com", verbose_name="IMAP хост")
    folder = models.CharField(max_length=50, default="INBOX", verbose_name="Папка")

    allowed_sender = models.CharField(max_length=255, verbose_name="Дозволений відправник")
    allowed_subject_keyword = models.CharField(max_length=100, blank=True, verbose_name="Ключове слово в темі")
    check_interval = models.PositiveIntegerField(default=30, verbose_name="Інтервал перевірки (сек)")

    def __str__(self):
        return f"{self.name} ({self.email})"

    class Meta:
        verbose_name = "Налаштування Email"
        verbose_name_plural = "Налаштування Email"
        # 🚀 ІНДЕКСИ для налаштувань
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['email']),
        ]


class ClientInteraction(models.Model):
    INTERACTION_TYPES = [
        ('call', 'Дзвінок'),
        ('email', 'Email'),
        ('meeting', 'Зустріч'),
        ('sms', 'SMS'),
        ('messenger', 'Месенджер'),
        ('social', 'Соціальні мережі'),
        ('other', 'Інше'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='interactions', verbose_name="Клієнт")
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES, verbose_name="Тип взаємодії")
    direction = models.CharField(max_length=10, choices=[
        ('incoming', 'Вхідний'),
        ('outgoing', 'Вихідний'),
    ], verbose_name="Напрямок")

    subject = models.CharField(max_length=255, verbose_name="Тема")
    description = models.TextField(blank=True, verbose_name="Опис")
    outcome = models.CharField(max_length=100, choices=[
        ('positive', 'Позитивний'),
        ('neutral', 'Нейтральний'),
        ('negative', 'Негативний'),
        ('follow_up', 'Потрібен наступний контакт'),
    ], verbose_name="Результат")

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Створив")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата")
    follow_up_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата наступного контакту")

    class Meta:
        verbose_name = "Взаємодія з клієнтом"
        verbose_name_plural = "Взаємодії з клієнтами"
        ordering = ['-created_at']


# 🔥 МОДЕЛЬ ДЛЯ ЗАДАЧ ПО КЛІЄНТАХ
class ClientTask(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Низький'),
        ('medium', 'Середній'),
        ('high', 'Високий'),
        ('urgent', 'Терміново'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Очікує'),
        ('in_progress', 'Виконується'),
        ('completed', 'Завершено'),
        ('cancelled', 'Скасовано'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='tasks', verbose_name="Клієнт")
    title = models.CharField(max_length=255, verbose_name="Назва задачі")
    description = models.TextField(blank=True, verbose_name="Опис")

    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Призначено")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', verbose_name="Пріоритет")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")

    due_date = models.DateTimeField(verbose_name="Дедлайн")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Створено")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершено")

    class Meta:
        verbose_name = "Задача по клієнту"
        verbose_name_plural = "Задачі по клієнтах"
        ordering = ['due_date', '-priority']
