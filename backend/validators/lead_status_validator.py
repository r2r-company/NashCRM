# backend/validators/lead_status_validator.py - ПОВНИЙ ВИПРАВЛЕНИЙ ВАЛІДАТОР

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
    Валідатор статусів заявок з контролем оплат та ціни
    """

    # 🔥 ПРАВИЛЬНА ПОСЛІДОВНІСТЬ СТАТУСІВ
    STATUS_FLOW = [
        'queued',  # 0 - У черзі
        'in_work',  # 1 - Менеджер обробляє
        'awaiting_prepayment',  # 2 - Очікую аванс
        'preparation',  # 3 - Адмін в роботі
        'warehouse_processing',  # 4 - Обробка на складі
        'warehouse_ready',  # 5 - 🆕 Готовий до відгрузки
        'on_the_way',  # 6 - В дорозі
        'completed',  # 7 - Завершено
        'declined'  # 8 - Відмовлено (окремо)
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
        🔥 ВИПРАВЛЕНА ЛОГІКА ПЕРЕХОДІВ
        """
        if current_status not in cls.STATUS_FLOW:
            return []

        allowed = []

        # Завжди можна відмовити (крім уже відмовлених)
        if current_status != 'declined':
            allowed.append('declined')

        # Завершені та відмовлені - фінальні
        if current_status in ['completed', 'declined']:
            return allowed

        current_index = cls.STATUS_FLOW.index(current_status)

        # 🔥 ЛОГІКА ПЕРЕХОДІВ ВПЕРЕД
        if current_index + 1 < len(cls.STATUS_FLOW) - 1:  # -1 бо declined окремо
            next_status = cls.STATUS_FLOW[current_index + 1]

            # Спеціальні перевірки для кожного переходу
            if next_status == 'warehouse_processing':
                # preparation → warehouse_processing: потрібна ціна + платіжні записи
                if lead and lead.price and lead.price > 0:
                    has_payments = LeadPaymentOperation.objects.filter(lead=lead).exists()
                    if has_payments:
                        allowed.append(next_status)

            elif next_status == 'warehouse_ready':
                # warehouse_processing → warehouse_ready: завжди можна
                allowed.append(next_status)

            elif next_status == 'on_the_way':
                # warehouse_ready → on_the_way: завжди можна
                allowed.append(next_status)

            elif next_status == 'completed':
                # on_the_way → completed: тільки при повній оплаті
                if lead and cls.is_fully_paid(lead):
                    allowed.append(next_status)

            else:
                # Інші переходи - без спеціальних умов
                allowed.append(next_status)

        # 🔥 ЛОГІКА ПЕРЕХОДІВ НАЗАД
        if current_index > 0:
            prev_status = cls.STATUS_FLOW[current_index - 1]

            # Спеціальні правила для переходів назад
            if current_status == 'warehouse_ready':
                # З warehouse_ready можна повернутися до warehouse_processing
                allowed.append('warehouse_processing')
            elif current_status == 'on_the_way':
                # З on_the_way можна повернутися до warehouse_ready (не warehouse_processing!)
                allowed.append('warehouse_ready')
            else:
                # Стандартний перехід назад
                allowed.append(prev_status)

        return list(set(allowed))  # Прибираємо дублікати

    @classmethod
    def can_transition(cls, current_status: str, new_status: str, lead: Lead = None) -> Tuple[bool, str]:
        """
        🔥 СПРОЩЕНА ПЕРЕВІРКА ПЕРЕХОДУ
        """
        if current_status == new_status:
            return True, "Статус не змінюється"

        allowed = cls.get_allowed_transitions(current_status, lead)

        if new_status not in allowed:
            return False, f"Перехід {current_status} → {new_status} заборонений"

        # 🔥 ДОДАТКОВІ ПЕРЕВІРКИ

        # Для warehouse_processing
        if current_status == 'preparation' and new_status == 'warehouse_processing':
            if not lead or not lead.price or lead.price <= 0:
                return False, "Потрібна ціна ліда > 0"
            if not LeadPaymentOperation.objects.filter(lead=lead).exists():
                return False, "Потрібен хоча б один платіжний запис"

        # Для completed
        if new_status == 'completed':
            if not lead or not lead.price or lead.price <= 0:
                return False, "Потрібна ціна ліда для завершення"
            if not cls.is_fully_paid(lead):
                payment_info = cls.get_payment_info(lead)
                return False, f"Не вистачає {payment_info['shortage']} грн"

        return True, "Перехід дозволено"

    @classmethod
    def get_next_required_action(cls, lead: Lead) -> str:
        """
        🔥 ОНОВЛЕНІ ОПИСИ ДІЙ
        """
        status = lead.status

        actions = {
            'queued': "Менеджер має взяти в роботу",
            'in_work': "Менеджер працює з клієнтом",
            'awaiting_prepayment': "Очікується аванс від клієнта",
            'preparation': "Адмін готує до передачі на склад (потрібна ціна + платіжні записи)",
            'warehouse_processing': "Склад обробляє замовлення",
            'warehouse_ready': "🆕 Товар готовий - очікує машину для доставки",
            'on_the_way': "Товар в дорозі - перевірте повну оплату перед завершенням",
            'completed': "✅ Замовлення завершено",
            'declined': "❌ Замовлення відмовлено"
        }

        # Додаткова логіка для статусу preparation
        if status == 'preparation' and lead:
            payment_info = cls.get_payment_info(lead)

            if payment_info['price'] <= 0:
                return "Адмін має встановити ціну ліда"

            has_payments = LeadPaymentOperation.objects.filter(lead=lead).exists()
            if not has_payments:
                return "Потрібно внести хоча б якусь суму в фінансові операції"

            return "Можна переводити на склад для обробки"

        # Додаткова логіка для статусу on_the_way
        if status == 'on_the_way' and lead:
            if not lead.price or lead.price <= 0:
                return "Спочатку потрібно встановити ціну ліда"

            if not cls.is_fully_paid(lead):
                payment_info = cls.get_payment_info(lead)
                return f"Потрібна доплата {payment_info['shortage']} грн перед завершенням"

            return "Можна завершувати заявку"

        return actions.get(status, "Невідомий статус")

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
            ('preparation', 'awaiting_prepayment'): "Повернути на оплату",
            ('warehouse_processing', 'warehouse_ready'): "Товар готовий до відгрузки",  # 🆕
            ('warehouse_processing', 'preparation'): "Повернути адміну",
            ('warehouse_ready', 'on_the_way'): "Відправити клієнту (машина забрала)",  # 🆕
            ('warehouse_ready', 'warehouse_processing'): "Повернути на обробку",  # 🆕
            ('on_the_way', 'completed'): "Завершити (при повній оплаті)",
            ('on_the_way', 'warehouse_ready'): "Повернути на склад",  # 🆕
        }

        # Відмова можлива з будь-якого статусу
        if to_status == 'declined':
            return "Відмовити від заявки"

        return descriptions.get((from_status, to_status), f"Перейти в {cls.STATUS_NAMES.get(to_status)}")

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
        try:
            payments = LeadPaymentOperation.objects.filter(lead=lead)

            expected = payments.filter(operation_type='expected').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')

            received = payments.filter(operation_type='received').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')

            price = lead.price or Decimal('0')

            return {
                'price': float(price),
                'expected': float(expected),
                'received': float(received),
                'shortage': float(max(price - received, Decimal('0'))),
                'overpaid': float(max(received - price, Decimal('0'))) if price > 0 else 0.0,
                'payment_percentage': round((received / price * 100), 2) if price > 0 else 100.0
            }
        except Exception as e:
            print(f"❌ Помилка при отриманні payment_info: {e}")
            return {
                'price': 0.0,
                'expected': 0.0,
                'received': 0.0,
                'shortage': 0.0,
                'overpaid': 0.0,
                'payment_percentage': 0.0
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
                'name': cls.STATUS_NAMES.get(current_status, current_status)
            },
            'new_status': {
                'code': new_status,
                'name': cls.STATUS_NAMES.get(new_status, new_status)
            },
            'payment_info': cls.get_payment_info(lead),
            'next_action': cls.get_next_required_action(lead) if not can_change else None
        }

        # Отримуємо доступні переходи
        available_transitions = cls.get_allowed_transitions(current_status, lead)
        result['available_transitions'] = [
            {
                'code': status,
                'name': cls.STATUS_NAMES.get(status, status),
                'description': cls._get_transition_description(current_status, status)
            }
            for status in available_transitions
        ]

        return result

    @classmethod
    def get_detailed_requirements(cls, current_status: str, target_status: str, lead: Lead = None) -> dict:
        """
        🔥 Детальні вимоги для переходу між статусами
        """
        requirements = {
            'status_transition': f"{cls.STATUS_NAMES.get(current_status)} → {cls.STATUS_NAMES.get(target_status)}",
            'requirements': [],
            'current_state': {},
            'missing': [],
            'blocking_factors': []
        }

        if not lead:
            requirements['blocking_factors'].append("Лід не знайдено")
            return requirements

        # Загальні вимоги для переходу на склад
        if current_status == 'preparation' and target_status == 'warehouse_processing':
            # Перевіряємо ціну
            price_ok = lead.price and lead.price > 0
            payment_records_count = LeadPaymentOperation.objects.filter(lead=lead).count()

            requirements['requirements'].extend([
                "Встановлена ціна ліда > 0",
                "Мінімум один запис у платіжних операціях"
            ])

            requirements['current_state'] = {
                'price': float(lead.price or 0),
                'price_set': price_ok,
                'payment_records_count': payment_records_count
            }

            if not price_ok:
                requirements['missing'].append("Ціна ліда не встановлена або = 0")
                requirements['blocking_factors'].append("Встановіть ціну ліда в полі 'price'")

            if payment_records_count == 0:
                requirements['missing'].append("Немає записів про платежі")
                requirements['blocking_factors'].append(
                    f"Додайте платіжний запис через POST /api/leads/{lead.id}/add-payment/")

        # Вимоги для завершення
        elif target_status == 'completed':
            payment_info = cls.get_payment_info(lead)
            fully_paid = cls.is_fully_paid(lead)

            requirements['requirements'].extend([
                "Ціна ліда > 0",
                f"Повна оплата ({payment_info['price']} грн)"
            ])

            requirements['current_state'] = {
                'price': payment_info['price'],
                'received': payment_info['received'],
                'shortage': payment_info['shortage'],
                'payment_percentage': payment_info['payment_percentage'],
                'fully_paid': fully_paid
            }

            if payment_info['price'] <= 0:
                requirements['missing'].append("Ціна ліда не встановлена")
                requirements['blocking_factors'].append("Встановіть ціну ліда")

            if not fully_paid:
                requirements['missing'].append(f"Не вистачає {payment_info['shortage']} грн")
                requirements['blocking_factors'].append(f"Додайте платіж на суму {payment_info['shortage']} грн")

        return requirements

    @classmethod
    def get_status_flow_info(cls) -> dict:
        """
        🔥 НОВА ФУНКЦІЯ: Інформація про весь flow статусів
        """
        return {
            'flow': cls.STATUS_FLOW,
            'names': cls.STATUS_NAMES,
            'total_statuses': len(cls.STATUS_FLOW),
            'final_statuses': ['completed', 'declined'],
            'active_statuses': [s for s in cls.STATUS_FLOW if s not in ['completed', 'declined']],
            'warehouse_statuses': ['warehouse_processing', 'warehouse_ready'],
            'manager_statuses': ['queued', 'in_work', 'awaiting_prepayment'],
            'admin_statuses': ['preparation'],
            'delivery_statuses': ['on_the_way']
        }

    @classmethod
    def get_status_by_role(cls, user_role: str) -> List[str]:
        """
        🔥 НОВА ФУНКЦІЯ: Статуси доступні для ролі
        """
        role_statuses = {
            'manager': ['queued', 'in_work', 'awaiting_prepayment'],
            'accountant': ['preparation', 'awaiting_prepayment', 'on_the_way', 'completed'],
            'warehouse': ['warehouse_processing', 'warehouse_ready'],
            'admin': cls.STATUS_FLOW.copy(),
            'superadmin': cls.STATUS_FLOW.copy()
        }

        return role_statuses.get(user_role, [])


def get_lead_requirements(lead_id: int, target_status: str) -> dict:
    """
    🔥 Отримати детальні вимоги для переходу
    """
    try:
        lead = Lead.objects.get(id=lead_id)
        return LeadStatusValidator.get_detailed_requirements(lead.status, target_status, lead)
    except Lead.DoesNotExist:
        return {
            'error': 'LEAD_NOT_FOUND',
            'message': f'Лід з ID {lead_id} не знайдено'
        }


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


def get_status_transitions_map() -> dict:
    """
    🔥 НОВА ФУНКЦІЯ: Карта всіх можливих переходів
    """
    transitions = {}

    for status in LeadStatusValidator.STATUS_FLOW:
        transitions[status] = {
            'name': LeadStatusValidator.STATUS_NAMES.get(status),
            'index': LeadStatusValidator.STATUS_FLOW.index(status),
            'can_transition_to': LeadStatusValidator.get_allowed_transitions(status),
            'is_final': status in ['completed', 'declined']
        }

    return transitions


def check_status_requirements(lead: Lead, target_status: str) -> dict:
    """
    🔥 НОВА ФУНКЦІЯ: Швидка перевірка вимог для статусу
    """
    current_status = lead.status

    # Базова перевірка переходу
    can_transition, reason = LeadStatusValidator.can_transition(current_status, target_status, lead)

    if not can_transition:
        return {
            'can_change': False,
            'reason': reason,
            'requirements_met': False
        }

    # Детальна перевірка вимог
    requirements = LeadStatusValidator.get_detailed_requirements(current_status, target_status, lead)

    return {
        'can_change': True,
        'reason': 'Перехід дозволено',
        'requirements_met': len(requirements['missing']) == 0,
        'missing_requirements': requirements['missing'],
        'blocking_factors': requirements['blocking_factors']
    }