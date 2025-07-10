# backend/utils/api_responses.py - ВИПРАВЛЕНИЙ ФАЙЛ

from rest_framework.response import Response
from django.utils import timezone
from enum import Enum

from backend.validators.lead_status_validator import LeadStatusValidator


class ErrorType(Enum):
    VALIDATION = "VALIDATION_ERROR"
    PERMISSION = "PERMISSION_ERROR"
    NOT_FOUND = "NOT_FOUND_ERROR"
    DUPLICATE = "DUPLICATE_ERROR"
    BUSINESS_RULE = "BUSINESS_RULE_ERROR"
    SYSTEM = "SYSTEM_ERROR"
    AUTHENTICATION = "AUTHENTICATION_ERROR"


class StatusChangeError(Enum):
    INVALID_TRANSITION = "INVALID_TRANSITION"
    MISSING_PAYMENT = "MISSING_PAYMENT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    MISSING_PRICE = "MISSING_PRICE"
    STATUS_TRANSITION_BLOCKED = "STATUS_TRANSITION_BLOCKED"


class APIResponse:
    """
    🔥 ВИПРАВЛЕНИЙ КЛАС - НЕ ЗАГОРТАЄ data В {result:, success:}
    """

    @staticmethod
    def success(data=None, message=None, meta=None, status_code=200):
        """
        ✅ Успішна відповідь - data передається НАПРЯМУ

        БУЛО (неправильно):
        {
            "data": {
                "result": [масив_лідів],
                "success": true
            }
        }

        СТАЛО (правильно):
        {
            "data": [масив_лідів]  # ← НАПРЯМУ!
        }
        """

        # 🔥 НЕ ЗАГОРТАЄМО data в {result:, success:}!
        response_data = {
            "data": data,  # ← НАПРЯМУ БЕЗ ЗАГОРТАННЯ!
            "meta": {
                "message": message,
                "errors": None,
                "timestamp": timezone.now().isoformat(),
                "status_code": status_code,
                **(meta or {})
            }
        }

        return Response(response_data, status=status_code)

    @staticmethod
    def error(error_type, message, details=None, field_errors=None, meta=None, status_code=400):
        """
        ❌ Помилка - data = null, все в meta
        """
        if isinstance(error_type, (ErrorType, StatusChangeError)):
            error_type = error_type.value

        response_data = {
            "data": None,  # ← При помилці data = null
            "meta": {
                "message": message,
                "errors": {
                    "type": error_type,
                    "message": message,
                    "details": details or {},
                    "field_errors": field_errors or {}
                },
                "timestamp": timezone.now().isoformat(),
                "status_code": status_code,
                **(meta or {})
            }
        }

        return Response(response_data, status=status_code)

    # Швидкі методи залишаються без змін
    @staticmethod
    def validation_error(message="Помилка валідації", field_errors=None, details=None, meta=None):
        return APIResponse.error(
            error_type=ErrorType.VALIDATION,
            message=message,
            field_errors=field_errors,
            details=details,
            meta=meta,
            status_code=400
        )

    @staticmethod
    def not_found_error(resource, resource_id=None, meta=None):
        message = f"{resource} не знайдено"
        if resource_id:
            message += f" (ID: {resource_id})"

        return APIResponse.error(
            error_type=ErrorType.NOT_FOUND,
            message=message,
            details={"resource": resource, "resource_id": resource_id},
            meta=meta,
            status_code=404
        )

    @staticmethod
    def duplicate_error(resource, duplicate_field, duplicate_value, existing_resource=None, meta=None):
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
    def system_error(message="Системна помилка", exception_details=None, meta=None):
        """🔥 Системна помилка сервера"""
        return APIResponse.error(
            error_type=ErrorType.SYSTEM,
            message=message,
            details=exception_details or {},
            meta=meta,
            status_code=500
        )

    @staticmethod
    def permission_error(message="Недостатньо прав", required_role=None, meta=None):
        """🔒 Помилка доступу"""
        details = {}
        if required_role:
            details["required_role"] = required_role

        return APIResponse.error(
            error_type=ErrorType.PERMISSION,
            message=message,
            details=details,
            meta=meta,
            status_code=403
        )

    @staticmethod
    def business_rule_error(message, rule_name=None, suggested_actions=None, meta=None):
        """📋 Порушення бізнес-правила"""
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


class LeadStatusResponse:
    """
    🔥 СПЕЦІАЛЬНІ ВІДПОВІДІ ДЛЯ СТАТУСІВ ЛІДІВ
    """

    @staticmethod
    def invalid_transition(current_status: str, attempted_status: str, available_transitions: list, reason: str = None):
        """❌ Недозволений перехід статусу"""

        transitions_info = []
        for transition in available_transitions:
            if isinstance(transition, dict):
                transitions_info.append(transition)
            else:
                transitions_info.append({
                    'code': transition,
                    'name': LeadStatusValidator.STATUS_NAMES.get(transition, transition),
                    'description': f'Перейти в {transition}'
                })

        error_message = reason or f"Неможливо перейти з '{LeadStatusValidator.STATUS_NAMES.get(current_status)}' в '{LeadStatusValidator.STATUS_NAMES.get(attempted_status)}'"

        return Response({
            "data": None,
            "meta": {
                "message": error_message,
                "errors": {
                    "type": "INVALID_TRANSITION",
                    "message": error_message,
                    "details": {
                        "current_status": {
                            "code": current_status,
                            "name": LeadStatusValidator.STATUS_NAMES.get(current_status)
                        },
                        "attempted_status": {
                            "code": attempted_status,
                            "name": LeadStatusValidator.STATUS_NAMES.get(attempted_status)
                        },
                        "available_transitions": transitions_info
                    }
                },
                "status_code": 400,
                "timestamp": timezone.now().isoformat()
            }
        }, status=400)

    @staticmethod
    def missing_payment(current_status, attempted_status, payment_info, required_amount=None):
        """💰 Недостатньо коштів для переходу"""
        if required_amount:
            message = f"Для переходу в '{attempted_status}' потрібно {required_amount} грн"
        else:
            message = f"Для переходу в '{attempted_status}' потрібна повна оплата"

        return APIResponse.error(
            error_type=StatusChangeError.INSUFFICIENT_FUNDS,
            message=message,
            details={
                "current_status": {
                    "code": current_status,
                    "name": current_status
                },
                "attempted_status": {
                    "code": attempted_status,
                    "name": attempted_status
                },
                "payment_info": payment_info,
                "required_amount": required_amount,
                "required_action": "Потрібно внести хоча б якусь суму в фінансові операції"
            },
            meta={"error_category": "status_change"},
            status_code=422
        )

    @staticmethod
    def missing_price(current_status, attempted_status, lead_id):
        """💸 Не встановлена ціна ліда"""
        return APIResponse.error(
            error_type=StatusChangeError.MISSING_PRICE,
            message=f"Неможливо перейти в '{attempted_status}' без встановленої ціни ліда",
            details={
                "current_status": {
                    "code": current_status,
                    "name": current_status
                },
                "attempted_status": {
                    "code": attempted_status,
                    "name": attempted_status
                },
                "lead_id": lead_id,
                "required_action": f"PATCH /api/leads/{lead_id}/ {{'price': 1000}}"
            },
            meta={"error_category": "status_change"},
            status_code=422
        )

    @staticmethod
    def success_transition(lead_id, old_status, new_status, lead_data, payment_info=None, next_action=None):
        """✅ Успішна зміна статусу"""
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


# 🔥 СТАРИЙ api_response ДЛЯ ЗВОРОТНОЇ СУМІСНОСТІ
def api_response(data=None, meta=None, message=None, errors=None, status_code=200):
    """
    ЗВОРОТНА СУМІСНІСТЬ: Стара функція тепер використовує новий APIResponse
    """
    if errors is not None or status_code >= 400:
        return APIResponse.error(
            error_type=ErrorType.SYSTEM,
            message=message or "Виникла помилка",
            details=errors if isinstance(errors, dict) else {"error": errors},
            meta=meta,
            status_code=status_code
        )
    else:
        return APIResponse.success(
            data=data,
            message=message,
            meta=meta,
            status_code=status_code
        )