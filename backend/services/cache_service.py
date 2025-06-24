# backend/services/cache_service.py
"""
Професійний сервіс управління кешем для ERP/CRM системи
Розроблено з урахуванням потреб бухгалтерського обліку
"""

from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from typing import Optional, List, Dict, Any
import logging
import json
import hashlib

logger = logging.getLogger('backend.cache_service')


class CacheService:
    """
    Професійний сервіс кешування для бухгалтерської системи
    """

    # Категорії даних з різними стратегіями кешування
    CACHE_CATEGORIES = {
        'financial': {
            'timeout': 30,  # Фінансові дані - 30 секунд
            'priority': 'high',
            'auto_invalidate': True
        },
        'operational': {
            'timeout': 60,  # Операційні дані - 1 хвилина
            'priority': 'medium',
            'auto_invalidate': True
        },
        'reference': {
            'timeout': 300,  # Довідкові дані - 5 хвилин
            'priority': 'low',
            'auto_invalidate': False
        },
        'static': {
            'timeout': 3600,  # Статичні дані - 1 година
            'priority': 'low',
            'auto_invalidate': False
        }
    }

    @classmethod
    def get_cache_key(cls, prefix: str, *args, **kwargs) -> str:
        """
        Генерує унікальний ключ кешу
        """
        # Створюємо стандартизований ключ
        key_parts = [prefix]

        # Додаємо аргументи
        for arg in args:
            if arg is not None:
                key_parts.append(str(arg))

        # Додаємо іменовані параметри
        for k, v in sorted(kwargs.items()):
            if v is not None:
                key_parts.append(f"{k}:{v}")

        # Створюємо хеш для довгих ключів
        key = "_".join(key_parts)
        if len(key) > 200:  # Обмеження Redis/Memcached
            key_hash = hashlib.md5(key.encode()).hexdigest()
            key = f"{prefix}_{key_hash}"

        return key

    @classmethod
    def set_financial_data(cls, key: str, data: Any, timeout: Optional[int] = None) -> None:
        """
        Кешування фінансових даних з найвищим пріоритетом
        """
        category = cls.CACHE_CATEGORIES['financial']
        final_timeout = timeout or category['timeout']

        cache_key = cls.get_cache_key('fin', key)
        cache.set(cache_key, data, final_timeout)

        # Логування для аудиту
        logger.info(f"💰 Кешовано фінансові дані: {cache_key} (TTL: {final_timeout}s)")

    @classmethod
    def get_financial_data(cls, key: str, default: Any = None) -> Any:
        """
        Отримання фінансових даних з кешу
        """
        cache_key = cls.get_cache_key('fin', key)
        data = cache.get(cache_key, default)

        if data is not None:
            logger.debug(f"💰 Фінансові дані з кешу: {cache_key}")
        else:
            logger.debug(f"💰 Фінансові дані НЕ в кеші: {cache_key}")

        return data

    @classmethod
    def set_operational_data(cls, key: str, data: Any, timeout: Optional[int] = None) -> None:
        """
        Кешування операційних даних (статуси лідів, воронка)
        """
        category = cls.CACHE_CATEGORIES['operational']
        final_timeout = timeout or category['timeout']

        cache_key = cls.get_cache_key('ops', key)
        cache.set(cache_key, data, final_timeout)

        logger.info(f"📊 Кешовано операційні дані: {cache_key} (TTL: {final_timeout}s)")

    @classmethod
    def get_operational_data(cls, key: str, default: Any = None) -> Any:
        """
        Отримання операційних даних
        """
        cache_key = cls.get_cache_key('ops', key)
        return cache.get(cache_key, default)

    @classmethod
    def set_reference_data(cls, key: str, data: Any, timeout: Optional[int] = None) -> None:
        """
        Кешування довідкових даних (менеджери, клієнти)
        """
        category = cls.CACHE_CATEGORIES['reference']
        final_timeout = timeout or category['timeout']

        cache_key = cls.get_cache_key('ref', key)
        cache.set(cache_key, data, final_timeout)

        logger.info(f"📋 Кешовано довідкові дані: {cache_key} (TTL: {final_timeout}s)")

    @classmethod
    def get_reference_data(cls, key: str, default: Any = None) -> Any:
        """
        Отримання довідкових даних
        """
        cache_key = cls.get_cache_key('ref', key)
        return cache.get(cache_key, default)

    @classmethod
    def invalidate_lead_related_cache(cls, lead_id: int, manager_id: Optional[int] = None,
                                      client_phone: Optional[str] = None) -> None:
        """
        Розумне очищення кешу при зміні ліда
        ЦЕ ГОЛОВНА ФУНКЦІЯ ДЛЯ ВИРІШЕННЯ ВАШОЇ ПРОБЛЕМИ!
        """
        keys_to_delete = []

        # 🚀 ФІНАНСОВІ ДАНІ (найважливіше)
        keys_to_delete.extend([
            cls.get_cache_key('fin', 'payments', lead_id),
            cls.get_cache_key('fin', 'lead_payments', lead_id),
            cls.get_cache_key('fin', 'payments', f'lead_{lead_id}'),
        ])

        # 🚀 ОПЕРАЦІЙНІ ДАНІ (воронка, статуси)
        keys_to_delete.extend([
            cls.get_cache_key('ops', 'funnel'),
            cls.get_cache_key('ops', 'funnel', 'None', 'None', 'None'),
            cls.get_cache_key('ops', 'funnel', None, None, None),
        ])

        if manager_id:
            keys_to_delete.extend([
                cls.get_cache_key('ops', 'funnel', None, None, manager_id),
                cls.get_cache_key('ops', 'funnel', 'None', 'None', manager_id),
            ])

        # 🚀 ЗВІТИ (всі варіанти)
        keys_to_delete.extend([
            cls.get_cache_key('ops', 'leads_report'),
            cls.get_cache_key('ops', 'detailed_report'),
        ])

        # 🚀 КЛІЄНТСЬКІ ДАНІ
        if client_phone:
            keys_to_delete.extend([
                cls.get_cache_key('ref', 'client_leads', client_phone),
                cls.get_cache_key('ref', 'client_payments', client_phone),
            ])

        # Видаляємо всі ключі
        for key in keys_to_delete:
            cache.delete(key)
            logger.info(f"🗑️ Видалено з кешу: {key}")

        # 🚀 ВИДАЛЯЄМО ПО ШАБЛОНАХ (якщо підтримується)
        patterns_to_delete = [
            'funnel_*',
            'leads_report_*',
            'detailed_report_*',
            'payments_*',
            f'*lead_{lead_id}*',
        ]

        for pattern in patterns_to_delete:
            try:
                # Намагаємося видалити по шаблону
                cache.delete_pattern(pattern)
                logger.info(f"🗑️ Видалено по шаблону: {pattern}")
            except (AttributeError, NotImplementedError):
                # Якщо backend не підтримує delete_pattern
                pass

        logger.info(f"🔄 Очищено кеш для ліда #{lead_id}")

    @classmethod
    def invalidate_manager_cache(cls, manager_id: int) -> None:
        """
        Очищення кешу при зміні менеджера
        """
        keys_to_delete = [
            cls.get_cache_key('ref', 'managers_list'),
            cls.get_cache_key('ref', 'managers'),
            cls.get_cache_key('ops', 'funnel', None, None, manager_id),
        ]

        for key in keys_to_delete:
            cache.delete(key)

        logger.info(f"🔄 Очищено кеш для менеджера #{manager_id}")

    @classmethod
    def invalidate_client_cache(cls, client_id: int, phone: Optional[str] = None) -> None:
        """
        Очищення кешу при зміні клієнта
        """
        keys_to_delete = [
            cls.get_cache_key('ref', 'client_leads', client_id),
            cls.get_cache_key('ref', 'client_payments', client_id),
        ]

        if phone:
            keys_to_delete.extend([
                cls.get_cache_key('ref', 'client_leads', phone),
                cls.get_cache_key('ref', 'client_payments', phone),
            ])

        for key in keys_to_delete:
            cache.delete(key)

        logger.info(f"🔄 Очищено кеш для клієнта #{client_id}")

    @classmethod
    def invalidate_all_reports(cls) -> None:
        """
        Повне очищення всіх звітів (використовувати обережно!)
        """
        patterns = [
            'fin_*',
            'ops_*',
            'funnel_*',
            'leads_report_*',
            'detailed_report_*',
            'payments_*',
        ]

        for pattern in patterns:
            try:
                cache.delete_pattern(pattern)
                logger.warning(f"🗑️ ПОВНЕ ОЧИЩЕННЯ по шаблону: {pattern}")
            except (AttributeError, NotImplementedError):
                pass

        logger.warning("🔄 ПОВНЕ ОЧИЩЕННЯ КЕШУ ЗВІТІВ")

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """
        Статистика використання кешу для моніторингу
        """
        try:
            # Якщо кеш підтримує статистику
            stats = cache.get_stats() if hasattr(cache, 'get_stats') else {}

            return {
                'backend': cache.__class__.__name__,
                'stats': stats,
                'categories': cls.CACHE_CATEGORIES,
                'timestamp': timezone.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Помилка отримання статистики кешу: {e}")
            return {'error': str(e)}

    @classmethod
    def warm_up_cache(cls) -> None:
        """
        Прогрів кешу основними даними
        """
        from backend.models import Lead, CustomUser

        try:
            # Прогріваємо список менеджерів
            managers = CustomUser.objects.filter(interface_type='accountant').count()
            cls.set_reference_data('managers_count', managers)

            # Прогріваємо базову статистику
            leads_count = Lead.objects.count()
            cls.set_operational_data('total_leads', leads_count)

            logger.info("🔥 Кеш прогрітий базовими даними")

        except Exception as e:
            logger.error(f"Помилка прогріву кешу: {e}")


# 🚀 ДЕКОРАТОР ДЛЯ АВТОМАТИЧНОГО КЕШУВАННЯ
def cache_result(category: str = 'operational', timeout: Optional[int] = None,
                 key_prefix: str = 'auto'):
    """
    Декоратор для автоматичного кешування результатів функцій

    Використання:
    @cache_result('financial', timeout=30, key_prefix='payments')
    def get_payments_sum(lead_id):
        return calculate_payments(lead_id)
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Створюємо ключ на основі функції та аргументів
            cache_key = CacheService.get_cache_key(
                key_prefix,
                func.__name__,
                *args,
                **kwargs
            )

            # Намагаємося отримати з кешу
            if category == 'financial':
                result = CacheService.get_financial_data(cache_key)
            elif category == 'operational':
                result = CacheService.get_operational_data(cache_key)
            elif category == 'reference':
                result = CacheService.get_reference_data(cache_key)
            else:
                result = cache.get(cache_key)

            if result is not None:
                return result

            # Виконуємо функцію та кешуємо результат
            result = func(*args, **kwargs)

            if category == 'financial':
                CacheService.set_financial_data(cache_key, result, timeout)
            elif category == 'operational':
                CacheService.set_operational_data(cache_key, result, timeout)
            elif category == 'reference':
                CacheService.set_reference_data(cache_key, result, timeout)
            else:
                cache.set(cache_key, result, timeout or 300)

            return result

        return wrapper

    return decorator


# 🚀 МІДЛВЕР ДЛЯ АВТОМАТИЧНОГО ОЧИЩЕННЯ КЕШУ
class SmartCacheMiddleware:
    """
    Мідлвер для автоматичного очищення кешу при зміні даних
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Якщо це POST/PUT/PATCH запит до API лідів
        if (request.method in ['POST', 'PUT', 'PATCH', 'DELETE'] and
                '/api/leads/' in request.path):
            # Очищуємо кеш після зміни даних
            CacheService.invalidate_all_reports()
            logger.info("🔄 Автоматичне очищення кешу після зміни лідів")

        return response


# 🚀 КОМАНДА DJANGO ДЛЯ УПРАВЛІННЯ КЕШЕМ
