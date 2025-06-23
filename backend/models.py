import re
from django.contrib.auth.models import User
from django.db import models


class CustomUser(models.Model):
    INTERFACE_CHOICES = [
        ('admin', 'Адміністратор'),
        ('accountant', 'Менеджер'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Користувач")
    interface_type = models.CharField(max_length=20, choices=INTERFACE_CHOICES, verbose_name="Тип інтерфейсу")

    def __str__(self):
        return f"{self.user.username} ({self.get_interface_type_display()})"

    class Meta:
        verbose_name = "Користувач інтерфейсу"
        verbose_name_plural = "Користувачі інтерфейсу"
        # 🚀 ІНДЕКСИ для швидкого пошуку менеджерів
        indexes = [
            models.Index(fields=['interface_type']),
            models.Index(fields=['user', 'interface_type']),
        ]


class Lead(models.Model):
    STATUS_CHOICES = [
        ('new', 'Новий'),
        ('queued', 'У черзі'),
        ('in_work', 'Обробляється менеджером'),
        ('awaiting_packaging', 'Очікую відповідь від складу'),
        ('on_the_way', 'В дорозі'),
        ('awaiting_cash', 'Очікую кошти від водія'),
        ('paid', 'Оплачено'),
        ('declined', 'Відмовлено'),
        ('completed', 'Завершено'),
    ]

    full_name = models.CharField(max_length=255, verbose_name="ПІБ")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    source = models.CharField(max_length=100, blank=True, verbose_name="Джерело")
    description = models.TextField(blank=True, verbose_name="Опис")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Ціна")
    delivery_number = models.CharField(max_length=100, blank=True, verbose_name="ТТН")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new', verbose_name="Статус")
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

    class Meta:
        verbose_name = "Лід"
        verbose_name_plural = "Ліди"
        # 🚀 КРИТИЧНІ ІНДЕКСИ для швидкості звітів і фільтрів
        indexes = [
            # Для воронки статусів (найчастіше використовується)
            models.Index(fields=['status']),

            # Для звітів по датах (created_at найбільш критичний)
            models.Index(fields=['created_at']),
            models.Index(fields=['status_updated_at']),

            # Для зв'язку з клієнтами через телефон
            models.Index(fields=['phone']),

            # Для фільтрів по менеджерах
            models.Index(fields=['assigned_to']),

            # Композитні індекси для складних запитів
            models.Index(fields=['assigned_to', 'status']),  # Звіти по менеджерах
            models.Index(fields=['status', 'created_at']),  # Воронка по датах
            models.Index(fields=['phone', 'status']),  # Клієнтські звіти
            models.Index(fields=['created_at', 'assigned_to']),  # Продуктивність менеджерів

            # Для фінансових звітів
            models.Index(fields=['status', 'price']),  # Завершені ліди з сумою
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

    full_name = models.CharField(max_length=255, verbose_name="ПІБ")
    phone = models.CharField(max_length=30, unique=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    company_name = models.CharField(max_length=255, blank=True, verbose_name="Назва компанії")
    type = models.CharField(max_length=20, choices=CLIENT_TYPE_CHOICES, default='individual', verbose_name="Тип")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Статус")
    notes = models.TextField(blank=True, verbose_name="Нотатки")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Менеджер")
    difficulty_rating = models.PositiveSmallIntegerField(
        default=1,
        choices=[(i, f"{i} зірок") for i in range(1, 6)],
        verbose_name="Рейтинг складності"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Створено")

    def save(self, *args, **kwargs):
        self.phone = self.normalize_phone(self.phone)
        super().save(*args, **kwargs)

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if digits.startswith("0"):
            digits = "38" + digits
        elif not digits.startswith("38") and len(digits) == 10:
            digits = "38" + digits
        return digits

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

    class Meta:
        verbose_name = "Клієнт"
        verbose_name_plural = "Клієнти"
        # 🚀 ІНДЕКСИ для швидкого пошуку клієнтів
        indexes = [
            # phone вже є unique, але додаємо для JOIN з лідами
            models.Index(fields=['phone']),
            models.Index(fields=['status']),
            models.Index(fields=['assigned_to']),
            models.Index(fields=['created_at']),
            models.Index(fields=['type', 'status']),  # Для звітів по типах клієнтів
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