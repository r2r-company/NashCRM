# backend/validators/lead_status_validator.py - ОНОВЛЕНИЙ ВАЛІДАТОР

"""
Валідатор переходів статусів лідів для ERP/CRM системи
Оновлений з новим статусом "Склад - готовий до відгрузки"
"""

from django.db.models import Sum
from backend.models import Lead, LeadPaymentOperation
from decimal import Decimal
from typing import List, Tuple, Optional


class LeadStatusValidator:
    """
    Валідатор статусів заявок з контролем оплат
    """

    # 🆕 ОНОВЛЕНА ПОСЛІДОВНІСТЬ СТАТУСІВ
    STATUS_FLOW = [
        'queued',                  # 0 - У черзі
        'in_work',                 # 1 - Менеджер обробляє
        'awaiting_prepayment',     # 2 - Очікую аванс
        'preparation',             # 3 - Адмін в роботі
        'warehouse_processing',    # 4 - Обробка на складі
        'warehouse_ready',         # 5 - 🆕 Склад - готовий до відгрузки
        'on_the_way',             # 6 - В дорозі
        'completed',              # 7 - Завершено
        'declined'                # 8 - Відмовлено
    ]

    # 🆕 ОНОВЛЕНІ НАЗВИ СТАТУСІВ
    STATUS_NAMES = {
        'queued': 'У черзі',
        'in_work': 'Обробляється менеджером',
        'awaiting_prepayment': 'Очікую аванс',
        'preparation': 'В роботу (адмін)',
        'warehouse_processing': 'Обробка на складі',
        'warehouse_ready': 'Склад - готовий до відгрузки',  # 🆕
        'on_the_way': 'В дорозі',
        'completed': 'Завершено',
        'declined': 'Відмовлено'
    }

    @classmethod
    def get_allowed_transitions(cls, current_status: str, lead: Lead = None) -> List[str]:
        """
        Отримати дозволені переходи з поточного статусу
        """
        if current_status not in cls.STATUS_FLOW:
            return []

        current_index = cls.STATUS_FLOW.index(current_status)
        allowed = []

        # Завжди можна відмовити (крім уже відмовлених)
        if current_status != 'declined':
            allowed.append('declined')

        # Завершені та відмовлені - фінальні статуси
        if current_status in ['completed', 'declined']:
            return allowed

        # Можна йти на один крок вперед
        if current_index + 1 < len(cls.STATUS_FLOW) - 1:  # -1 бо declined окремо
            next_status = cls.STATUS_FLOW[current_index + 1]

            # Спеціальна перевірка для completed - тільки при повній оплаті
            if next_status == 'completed' and lead:
                if lead.price and lead.price > 0 and cls.is_fully_paid(lead):
                    allowed.append(next_status)

            # Перевірка для warehouse_processing (потрібні записи про оплату)
            elif next_status == 'warehouse_processing' and lead and current_status == 'preparation':
                has_any_payment_record = LeadPaymentOperation.objects.filter(lead=lead).exists()
                if has_any_payment_record:
                    allowed.append(next_status)

            # 🆕 НОВИЙ СТАТУС: warehouse_ready
            elif next_status == 'warehouse_ready':
                # Можна переходити коли склад обробив замовлення
                allowed.append(next_status)

            else:
                allowed.append(next_status)

        # Можна йти на один крок назад (крім queued)
        if current_index > 0:
            prev_status = cls.STATUS_FLOW[current_index - 1]
            allowed.append(prev_status)

        return allowed

    @classmethod
    def get_next_required_action(cls, lead: Lead) -> str:
        """
        Що потрібно зробити далі з лідом
        """
        status = lead.status
        payment_info = cls.get_payment_info(lead)

        if status == 'queued':
            return "Менеджер має взяти в роботу"

        elif status == 'in_work':
            return "Менеджер має поговорити з клієнтом та отримати оплату"

        elif status == 'awaiting_prepayment':
            return "Очікується надходження авансу від клієнта"

        elif status == 'preparation':
            if payment_info['price'] <= 0:
                return "Адмін має встановити ціну ліда"
            else:
                has_any_payment_record = LeadPaymentOperation.objects.filter(lead=lead).exists() if lead else False
                if not has_any_payment_record:
                    return "Потрібно внести хоча б якусь суму в фінансові операції"
                else:
                    return "Можна переводити на склад для обробки"

        elif status == 'warehouse_processing':
            return "Склад обробляє замовлення - комплектація, пакування"

        elif status == 'warehouse_ready':  # 🆕 НОВИЙ СТАТУС
            return "Товар готовий до відгрузки - очікує машину для доставки"

        elif status == 'on_the_way':
            if not lead.price or lead.price <= 0:
                return "Спочатку потрібно встановити ціну ліда в статусі 'preparation'"
            elif not cls.is_fully_paid(lead):
                payment_info = cls.get_payment_info(lead)
                return f"Потрібна доплата {payment_info['shortage']} грн перед завершенням (від ціни {payment_info['price']} грн)"
            else:
                return "Можна завершувати заявку"

        elif status == 'completed':
            return "Заявка завершена"

        elif status == 'declined':
            return "Заявка відмовлена"

        return "Невідомий статус"

    @classmethod
    def _get_transition_description(cls, from_status: str, to_status: str) -> str:
        """
        Опис що означає конкретний перехід
        """
        descriptions = {
            ('queued', 'in_work'): "Взяти в роботу",
            ('in_work', 'awaiting_prepayment'): "Передати на оплату",
            ('in_work', 'queued'): "Повернути в чергу",
            ('awaiting_prepayment', 'preparation'): "Передати адміну (аванс отримано)",
            ('awaiting_prepayment', 'in_work'): "Повернути менеджеру",
            ('preparation', 'warehouse_processing'): "Передати на склад для обробки",
            ('preparation', 'in_work'): "Повернути менеджеру",
            ('warehouse_processing', 'warehouse_ready'): "Товар готовий до відгрузки",  # 🆕
            ('warehouse_processing', 'preparation'): "Повернути адміну",
            ('warehouse_ready', 'on_the_way'): "Відправити клієнту (машина забрала)",  # 🆕
            ('warehouse_ready', 'warehouse_processing'): "Повернути на обробку",  # 🆕
            ('on_the_way', 'completed'): "Завершити (при повній оплаті)",
            ('on_the_way', 'warehouse_ready'): "Повернути на склад",  # 🆕 (замість warehouse_processing)
        }

        # Відмова можлива з будь-якого статусу
        if to_status == 'declined':
            return "Відмовити від заявки"

        return descriptions.get((from_status, to_status), f"Перейти в {cls.STATUS_NAMES.get(to_status)}")

    # Всі інші методи залишаються без змін...
    @classmethod
    def can_transition(cls, current_status: str, new_status: str, lead: Lead = None) -> Tuple[bool, str]:
        """
        Перевірити чи можна перейти з одного статусу в інший
        """
        if current_status == new_status:
            return True, "Статус не змінюється"

        allowed = cls.get_allowed_transitions(current_status, lead)

        if new_status not in allowed:
            return False, f"Неможливо перейти з '{cls.STATUS_NAMES.get(current_status)}' в '{cls.STATUS_NAMES.get(new_status)}'"

        # Додаткові перевірки для completed
        if new_status == 'completed' and lead:
            if not lead.price or lead.price <= 0:
                return False, f"Неможливо завершити - не встановлена ціна ліда"

            if not cls.is_fully_paid(lead):
                payment_info = cls.get_payment_info(lead)
                shortage = payment_info['price'] - payment_info['received']
                return False, f"Неможливо завершити - не вистачає {shortage} грн для повної оплати"

        # Валідація для warehouse_processing
        if current_status == 'preparation' and new_status == 'warehouse_processing' and lead:
            has_any_payment_record = LeadPaymentOperation.objects.filter(lead=lead).exists()
            if not has_any_payment_record:
                return False, f"Неможливо передати на склад - немає записів про оплату"

        return True, "Перехід дозволено"

    @classmethod
    def is_fully_paid(cls, lead: Lead) -> bool:
        """
        Перевірити чи лід повністю оплачений
        """
        if not lead.price or lead.price <= 0:
            return False

        payment_info = cls.get_payment_info(lead)
        return payment_info['received'] >= payment_info['price']

    @classmethod
    def get_payment_info(cls, lead: Lead) -> dict:
        """
        Отримати інформацію про оплати ліда
        """
        payments = LeadPaymentOperation.objects.filter(lead=lead)

        expected = payments.filter(operation_type='expected').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        received = payments.filter(operation_type='received').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        price = lead.price or Decimal('0')

        return {
            'price': price,
            'expected': expected,
            'received': received,
            'shortage': max(price - received, Decimal('0')),
            'overpaid': max(received - price, Decimal('0')) if price > 0 else Decimal('0'),
            'payment_percentage': round((received / price * 100), 2) if price > 0 else 100
        }

    @classmethod
    def validate_status_change(cls, lead: Lead, new_status: str, user=None) -> dict:
        """
        Повна валідація зміни статусу з детальною інформацією
        """
        current_status = lead.status
        can_change, reason = cls.can_transition(current_status, new_status, lead)

        result = {
            'allowed': can_change,
            'reason': reason,
            'current_status': {
                'code': current_status,
                'name': cls.STATUS_NAMES.get(current_status)
            },
            'new_status': {
                'code': new_status,
                'name': cls.STATUS_NAMES.get(new_status)
            },
            'payment_info': cls.get_payment_info(lead),
            'next_action': cls.get_next_required_action(lead) if not can_change else None
        }

        result['available_transitions'] = [
            {
                'code': status,
                'name': cls.STATUS_NAMES.get(status),
                'description': cls._get_transition_description(current_status, status)
            }
            for status in cls.get_allowed_transitions(current_status, lead)
        ]

        return result


# Допоміжна функція для використання в views
def validate_lead_status_change(lead_id: int, new_status: str, user=None) -> dict:
    """
    Зручна функція для валідації в контролерах
    """
    try:
        lead = Lead.objects.get(id=lead_id)
        return LeadStatusValidator.validate_status_change(lead, new_status, user)
    except Lead.DoesNotExist:
        return {
            'allowed': False,
            'reason': f'Лід з ID {lead_id} не знайдено',
            'error': 'LEAD_NOT_FOUND'
        }