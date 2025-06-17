from backend.models import Lead, Client
from django.contrib.auth.models import User
from backend.ws_notify import notify_lead_created


def get_free_manager() -> User | None:
    # Всі менеджери
    managers = User.objects.all()

    for manager in managers:
        active_lead = Lead.objects.filter(assigned_to=manager, status='in_work').exists()
        if not active_lead:
            return manager  # перший вільний

    return None


def create_lead_with_logic(data: dict) -> tuple[Lead, dict]:
    from backend.models import Lead as LeadModel

    context = {}

    # 1. Клієнт
    client, created = Client.objects.get_or_create(
        phone=data['phone'],
        defaults={
            'full_name': data.get('full_name', ''),
            'email': data.get('email', ''),
            'assigned_to': None
        }
    )
    context['client_created'] = created
    context['client_assigned_to'] = client.assigned_to.username if client.assigned_to else None

    # 2. Менеджер
    manager = client.assigned_to or data.get('assigned_to')
    context['manager_initial'] = manager.username if manager else None

    if not manager:
        manager = get_free_manager()
        context['manager_auto_found'] = manager.username if manager else None

    # 3. Статус і позиція в черзі
    status = 'queued'
    queued_position = None

    if manager:
        active = LeadModel.objects.filter(assigned_to=manager, status='in_work').exists()
        if not active:
            status = 'in_work'
            context['reason'] = 'Менеджер вільний — лід одразу в роботу'
        else:
            status = 'queued'
            last_position = LeadModel.objects.filter(
                assigned_to=manager, status='queued'
            ).count()
            queued_position = last_position + 1
            context['reason'] = f'Менеджер зайнятий — лід у черзі #{queued_position}'
    else:
        context['reason'] = 'Не знайдено вільного менеджера — лід без призначення'

    # 4. Створення ліда
    lead = Lead.objects.create(
        full_name=data.get('full_name', client.full_name),
        phone=data['phone'],
        email=data.get('email', client.email),
        source=data.get('source', ''),
        description=data.get('description', ''),
        price=data.get('price', 0),
        delivery_number=data.get('delivery_number', ''),
        status=status,
        assigned_to=manager,
        queued_position=queued_position
    )

    context['final_status'] = status
    context['assigned_to'] = manager.username if manager else None
    context['queued_position'] = queued_position


    return lead, context