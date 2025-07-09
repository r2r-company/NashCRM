# backend/utils/api_responses.py - СТАНДАРТНІ API ВІДПОВІДІ

from rest_framework.response import Response
from django.utils import timezone
from typing import Dict, Any, Optional, List, Union
from enum import Enum


class ErrorType(Enum):
    """Стандартні типи помилок"""
    VALIDATION = "VALIDATION_ERROR"
    PERMISSION = "PERMISSION_ERROR"
    NOT_FOUND = "NOT_FOUND_ERROR"
    DUPLICATE = "DUPLICATE_ERROR"
    BUSINESS_RULE = "BUSINESS_RULE_ERROR"
    SYSTEM = "SYSTEM_ERROR"


class StatusChangeError(Enum):
    """Типи помилок для зміни статусів лідів"""
    INVALID_TRANSITION = "INVALID_TRANSITION"
    MISSING_PAYMENT = "MISSING_PAYMENT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    MISSING_PRICE = "MISSING_PRICE"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"


class APIResponse:
    """
    Клас для створення стандартних API відповідей
    """

    @staticmethod
    def success(data=None, message=None, meta=None, status_code=200):
        """
        ✅ Успішна відповідь

        Структура:
        {
            "success": true,
            "data": { ... },
            "message": "Операція успішна",
            "errors": null,
            "meta": { "timestamp": "...", "status_code": 200 }
        }
        """
        response_data = {
            "success": True,
            "data": data or {},
            "message": message,
            "errors": None,
            "meta": {
                "timestamp": timezone.now().isoformat(),
                "status_code": status_code,
                **(meta or {})
            }
        }

        return Response(response_data, status=status_code)

    @staticmethod
    def error(error_type, message, details=None, field_errors=None, meta=None, status_code=400):
        """
        ❌ Помилка

        Структура:
        {
            "success": false,
            "data": null,
            "message": "Опис помилки",
            "errors": {
                "type": "ERROR_TYPE",
                "message": "Опис помилки",
                "details": { ... },
                "field_errors": { "field": ["помилка1", "помилка2"] }
            },
            "meta": { "timestamp": "...", "status_code": 400 }
        }
        """
        # Якщо передано enum - беремо його значення
        if isinstance(error_type, (ErrorType, StatusChangeError)):
            error_type = error_type.value

        response_data = {
            "success": False,
            "data": None,
            "message": message,
            "errors": {
                "type": error_type,
                "message": message,
                "details": details or {},
                "field_errors": field_errors or {}
            },
            "meta": {
                "timestamp": timezone.now().isoformat(),
                "status_code": status_code,
                **(meta or {})
            }
        }

        return Response(response_data, status=status_code)

    @staticmethod
    def validation_error(message="Помилка валідації", field_errors=None, details=None, meta=None):
        """
        📝 Помилка валідації (400)

        Використовується для: невалідні дані форм, обов'язкові поля, формат даних
        """
        return APIResponse.error(
            error_type=ErrorType.VALIDATION,
            message=message,
            field_errors=field_errors,
            details=details,
            meta=meta,
            status_code=400
        )

    @staticmethod
    def duplicate_error(resource, duplicate_field, duplicate_value, existing_resource=None, meta=None):
        """
        🔄 Помилка дублікату (409)

        Використовується для: дублікати телефонів, номерів замовлень, email
        """
        message = f"{resource} з {duplicate_field} '{duplicate_value}' вже існує"

        return APIResponse.error(
            error_type=ErrorType.DUPLICATE,
            message=message,
            details={
                "resource": resource,
                "duplicate_field": duplicate_field,
                "duplicate_value": duplicate_value,
                "existing_resource": existing_resource or {}
            },
            meta=meta,
            status_code=409
        )

    @staticmethod
    def not_found_error(resource, resource_id=None, meta=None):
        """
        🔍 Ресурс не знайдено (404)

        Використовується для: лід не знайдено, клієнт не існує
        """
        message = f"{resource} не знайдено"
        if resource_id:
            message += f" (ID: {resource_id})"

        return APIResponse.error(
            error_type=ErrorType.NOT_FOUND,
            message=message,
            details={
                "resource": resource,
                "resource_id": resource_id
            },
            meta=meta,
            status_code=404
        )

    @staticmethod
    def permission_error(message="Недостатньо прав доступу", required_role=None, meta=None):
        """
        🔒 Помилка доступу (403)

        Використовується для: немає прав, тільки для адміністраторів
        """
        return APIResponse.error(
            error_type=ErrorType.PERMISSION,
            message=message,
            details={
                "required_role": required_role
            },
            meta=meta,
            status_code=403
        )

    @staticmethod
    def business_rule_error(message, rule_name=None, suggested_actions=None, meta=None):
        """
        📋 Порушення бізнес-правил (422)

        Використовується для: не можна видалити, блокування операцій
        """
        return APIResponse.error(
            error_type=ErrorType.BUSINESS_RULE,
            message=message,
            details={
                "rule_name": rule_name,
                "suggested_actions": suggested_actions or []
            },
            meta=meta,
            status_code=422
        )

    @staticmethod
    def system_error(message, exception_details=None, meta=None):
        """
        🚨 Системна помилка (500)

        Використовується для: помилки бази даних, внутрішні помилки
        """
        return APIResponse.error(
            error_type=ErrorType.SYSTEM,
            message=message,
            details={
                "exception_details": exception_details
            },
            meta=meta,
            status_code=500
        )


class LeadStatusResponse:
    """
    Спеціальні відповіді для роботи зі статусами лідів
    """

    @staticmethod
    def invalid_transition(current_status, attempted_status, available_transitions, reason=None):
        """
        🔄 Неможливий перехід статусу

        Структура errors.details:
        {
            "current_status": "queued",
            "attempted_status": "completed",
            "available_transitions": [
                {"code": "in_work", "name": "В роботі", "description": "Взяти в роботу"}
            ],
            "reason": "Опис чому неможливо"
        }
        """
        message = reason or f"Неможливо змінити статус з '{current_status}' на '{attempted_status}'"

        return APIResponse.error(
            error_type=StatusChangeError.INVALID_TRANSITION,
            message=message,
            details={
                "current_status": current_status,
                "attempted_status": attempted_status,
                "available_transitions": available_transitions or [],
                "reason": reason
            },
            meta={"error_category": "status_change"},
            status_code=422
        )

    @staticmethod
    def missing_payment(current_status, attempted_status, payment_info, required_amount=None):
        """
        💰 Недостатньо коштів для переходу

        Структура errors.details:
        {
            "current_status": "on_the_way",
            "attempted_status": "completed",
            "payment_info": {
                "price": 1000,
                "received": 500,
                "shortage": 500
            },
            "required_amount": 500
        }
        """
        if required_amount:
            message = f"Для переходу в '{attempted_status}' потрібно {required_amount} грн"
        else:
            message = f"Для переходу в '{attempted_status}' потрібна повна оплата"

        return APIResponse.error(
            error_type=StatusChangeError.INSUFFICIENT_FUNDS,
            message=message,
            details={
                "current_status": current_status,
                "attempted_status": attempted_status,
                "payment_info": payment_info,
                "required_amount": required_amount
            },
            meta={"error_category": "status_change"},
            status_code=422
        )

    @staticmethod
    def missing_price(current_status, attempted_status, lead_id):
        """
        💸 Не встановлена ціна ліда

        Структура errors.details:
        {
            "current_status": "preparation",
            "attempted_status": "warehouse_processing",
            "lead_id": 123,
            "required_action": "PATCH /api/leads/123/ {'price': 1000}"
        }
        """
        return APIResponse.error(
            error_type=StatusChangeError.MISSING_PRICE,
            message=f"Неможливо перейти в '{attempted_status}' без встановленої ціни ліда",
            details={
                "current_status": current_status,
                "attempted_status": attempted_status,
                "lead_id": lead_id,
                "required_action": f"PATCH /api/leads/{lead_id}/ {{'price': 1000}}"
            },
            meta={"error_category": "status_change"},
            status_code=422
        )

    @staticmethod
    def success_transition(lead_id, old_status, new_status, lead_data, payment_info=None, next_action=None):
        """
        ✅ Успішна зміна статусу

        Структура data:
        {
            "lead": { ... },
            "status_change": {
                "from": "queued",
                "to": "in_work",
                "timestamp": "2025-01-01T10:00:00Z"
            },
            "payment_info": { ... },
            "next_action": "Менеджер має поговорити з клієнтом"
        }
        """
        return APIResponse.success(
            data={
                "lead": lead_data,
                "status_change": {
                    "from": old_status,
                    "to": new_status,
                    "timestamp": timezone.now().isoformat()
                },
                "payment_info": payment_info or {},
                "next_action": next_action
            },
            message=f"Статус успішно змінено: {old_status} → {new_status}",
            meta={
                "lead_id": lead_id,
                "change_type": "status_update"
            }
        )


# 🔥 ПРИКЛАДИ ВИКОРИСТАННЯ:

"""
# 1. Успішна відповідь
return APIResponse.success(
    data={"leads": [...]},
    message="Ліди успішно завантажено",
    meta={"total_count": 150}
)

# 2. Помилка валідації
return APIResponse.validation_error(
    message="Невалідні дані",
    field_errors={
        "phone": ["Телефон обов'язковий"],
        "email": ["Невалідний формат email"]
    }
)

# 3. Дублікат телефону
return APIResponse.duplicate_error(
    resource="Лід",
    duplicate_field="телефон",
    duplicate_value="+380123456789",
    existing_resource={"id": 123, "name": "Іван"}
)

# 4. Лід не знайдено
return APIResponse.not_found_error(
    resource="Лід",
    resource_id=999
)

# 5. Неможливий перехід статусу
return LeadStatusResponse.invalid_transition(
    current_status="queued",
    attempted_status="completed",
    available_transitions=[
        {"code": "in_work", "name": "В роботі"}
    ],
    reason="Не можна перестрибувати етапи"
)

# 6. Недостатньо коштів
return LeadStatusResponse.missing_payment(
    current_status="on_the_way",
    attempted_status="completed",
    payment_info={
        "price": 1000,
        "received": 500,
        "shortage": 500
    },
    required_amount=500
)

# 7. Успішна зміна статусу
return LeadStatusResponse.success_transition(
    lead_id=123,
    old_status="queued",
    new_status="in_work",
    lead_data={"id": 123, "name": "Іван"},
    next_action="Менеджер має зателефонувати клієнту"
)
"""