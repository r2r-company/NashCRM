# Файл: backend/middleware.py

import time
import logging
from django.db import connection
from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger('nashcrm.performance')


class PerformanceMiddleware:
    """
    Middleware для моніторингу продуктивності API
    Логує повільні запити та кількість SQL запитів
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Засікаємо час початку
        start_time = time.time()

        # Запам'ятовуємо кількість запитів до БД на початку
        initial_queries = len(connection.queries) if settings.DEBUG else 0

        # Обробляємо запит
        response = self.get_response(request)

        # Розраховуємо час виконання
        duration = time.time() - start_time

        # Рахуємо кількість SQL запитів
        query_count = len(connection.queries) - initial_queries if settings.DEBUG else 0

        # Логування для API ендпоінтів
        if request.path.startswith('/api/'):
            self._log_api_performance(request, response, duration, query_count)

        # Додаємо заголовки для розробки
        if settings.DEBUG:
            response['X-Query-Count'] = str(query_count)
            response['X-Response-Time'] = f"{duration:.3f}s"

        return response

    def _log_api_performance(self, request, response, duration, query_count):
        """Логування продуктивності API"""

        # Визначаємо тип запиту
        method = request.method
        path = request.path
        status_code = response.status_code

        # Створюємо повідомлення про продуктивність
        user = getattr(request.user, 'username', 'anonymous') if hasattr(request, 'user') else 'anonymous'

        # Визначаємо рівень логування БЕЗ ЕМОДЗІ (для Windows)
        if duration > 3.0:  # Дуже повільні запити (>3 сек)
            level = 'ERROR'
            message = "CRITICAL SLOW REQUEST"
        elif duration > 1.0:  # Повільні запити (1-3 сек)
            level = 'WARNING'
            message = "SLOW REQUEST"
        elif query_count > 10:  # Багато SQL запитів
            level = 'WARNING'
            message = "MANY SQL QUERIES"
        else:
            level = 'INFO'
            message = "NORMAL REQUEST"

        # Форматуємо лог БЕЗ ЕМОДЗІ
        log_message = (
            f"{message} | "
            f"{method} {path} | "
            f"Status: {status_code} | "
            f"Time: {duration:.3f}s | "
            f"Queries: {query_count} | "
            f"User: {user}"
        )

        # Логуємо відповідно до рівня
        if level == 'ERROR':
            logger.error(log_message)
            # Додатково логуємо SQL запити для критично повільних запитів
            if settings.DEBUG and query_count > 0:
                self._log_slow_queries(connection.queries[-query_count:])
        elif level == 'WARNING':
            logger.warning(log_message)
        else:
            logger.info(log_message)

    def _log_slow_queries(self, queries):
        """Логування повільних SQL запитів"""
        logger.error("SQL QUERIES FOR ANALYSIS:")

        for i, query in enumerate(queries, 1):
            sql = query.get('sql', 'Unknown')
            time_taken = query.get('time', 'Unknown')

            # Скорочуємо дуже довгі запити
            if len(sql) > 200:
                sql = sql[:200] + "..."

            logger.error(f"   {i}. Time: {time_taken}s | SQL: {sql}")


class SQLQueryCountMiddleware:
    """
    Додатковий middleware для детального аналізу SQL запитів
    Використовуйте тільки для розробки!
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.DEBUG:
            return self.get_response(request)

        # Очищуємо попередні запити
        if hasattr(connection, 'queries_log'):
            connection.queries_log.clear()

        response = self.get_response(request)

        # Аналізуємо дублікати запитів
        if request.path.startswith('/api/'):
            self._analyze_duplicate_queries(request.path)

        return response

    def _analyze_duplicate_queries(self, path):
        """Аналіз дублікатів SQL запитів"""
        queries = connection.queries

        if not queries:
            return

        # Групуємо запити по SQL
        query_groups = {}
        for query in queries:
            sql = query['sql']
            if sql in query_groups:
                query_groups[sql] += 1
            else:
                query_groups[sql] = 1

        # Знаходимо дублікати
        duplicates = {sql: count for sql, count in query_groups.items() if count > 1}

        if duplicates:
            logger.warning(f"DUPLICATE SQL FOR {path}:")
            for sql, count in duplicates.items():
                # Скорочуємо SQL для читабельності
                short_sql = sql[:100] + "..." if len(sql) > 100 else sql
                logger.warning(f"   {count}x: {short_sql}")


# Декоратор для вимірювання часу виконання функцій
def measure_time(func_name=None):
    """
    Декоратор для вимірювання часу виконання функцій

    Використання:
    @measure_time("Розрахунок звіту")
    def calculate_report():
        # ваш код
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            name = func_name or func.__name__
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                if duration > 0.5:  # Логуємо тільки якщо > 0.5 сек
                    logger.info(f"TIMING {name}: {duration:.3f}s")

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"ERROR {name} FAILED after {duration:.3f}s: {str(e)}")
                raise

        return wrapper

    return decorator


# Контекстний менеджер для вимірювання блоків коду
class TimingContext:
    """
    Контекстний менеджер для вимірювання часу виконання блоків коду

    Використання:
    with TimingContext("Обробка клієнтів"):
        # ваш код
    """

    def __init__(self, operation_name):
        self.operation_name = operation_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is None:
            if duration > 0.1:  # Логуємо тільки якщо > 0.1 сек
                logger.info(f"TIMING {self.operation_name}: {duration:.3f}s")
        else:
            logger.error(f"ERROR {self.operation_name} FAILED after {duration:.3f}s: {exc_val}")

        return False  # Не пригнічуємо виключення


# Утиліти для аналізу продуктивності
class PerformanceAnalyzer:
    """Клас для аналізу продуктивності додатка"""

    @staticmethod
    def analyze_slow_endpoints():
        """Аналіз найповільніших ендпоінтів"""
        # Тут можна додати логіку збору статистики з логів
        pass

    @staticmethod
    def get_database_stats():
        """Статистика використання бази даних"""
        from django.db import connection

        stats = {
            'total_queries': len(connection.queries) if settings.DEBUG else 0,
            'unique_queries': 0,
            'duplicate_queries': []
        }

        if settings.DEBUG:
            unique_queries = set(q['sql'] for q in connection.queries)
            stats['unique_queries'] = len(unique_queries)

            # Знаходимо дублікати
            query_counts = {}
            for query in connection.queries:
                sql = query['sql']
                query_counts[sql] = query_counts.get(sql, 0) + 1

            stats['duplicate_queries'] = [
                {'sql': sql[:100] + '...', 'count': count}
                for sql, count in query_counts.items()
                if count > 1
            ]

        return stats

    @staticmethod
    def memory_usage():
        """Отримання інформації про використання пам'яті"""
        try:
            import psutil
            import os

            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            return {
                'rss': memory_info.rss / 1024 / 1024,  # MB
                'vms': memory_info.vms / 1024 / 1024,  # MB
                'percent': process.memory_percent()
            }
        except ImportError:
            return {'error': 'psutil не встановлено'}


print("Performance Middleware завантажено успішно (Windows-friendly version)!")