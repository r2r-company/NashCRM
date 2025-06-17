from backend.models import Lead
from django.contrib.auth.models import User


def assign_next_lead(manager: User):
    """
    Дає менеджеру наступного ліда з черги
    """
    # Перевірка, чи є вже активний лід
    active = Lead.objects.filter(assigned_to=manager, status='in_work').first()
    if active:
        return active  # вже є активний — новий не видаємо

    next_lead = Lead.objects.filter(
        assigned_to=manager,
        status='queued'
    ).order_by('created_at').first()

    if next_lead:
        next_lead.status = 'in_work'
        next_lead.save()
        return next_lead

    return None


def on_lead_closed(lead: Lead):
    """
    Викликається, коли лід завершено (paid або declined)
    """
    if lead.status in ['paid', 'declined'] and lead.assigned_to:
        assign_next_lead(lead.assigned_to)
