# backend/ws_notify.py
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def notify_lead_created(lead):
    if not lead.assigned_to:
        return

    channel_layer = get_channel_layer()
    group = f"manager_{lead.assigned_to.id}"

    async_to_sync(channel_layer.group_send)(
        group,
        {
            "type": "send_new_lead",
            "data": {
                "id": lead.id,
                "full_name": lead.full_name,
                "status": lead.status,
            }
        }
    )
