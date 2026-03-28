"""
whatsapp.py — WhatsApp Cloud API wrapper.
One function per message type. Everything else calls these.
"""
import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)
BASE_URL = "https://graph.facebook.com/v19.0"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


async def _post(phone_number_id: str, payload: dict) -> httpx.Response:
    url = f"{BASE_URL}/{phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=_headers())
    if resp.status_code not in (200, 201):
        logger.error(f"WhatsApp error {resp.status_code}: {resp.text[:300]}")
    return resp


async def send_text(
    phone: str,
    message: str,
    phone_number_id: str | None = None,
) -> httpx.Response:
    """Send a plain-text WhatsApp message."""
    pid = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message, "preview_url": False},
    }
    return await _post(pid, payload)


async def send_interactive_buttons(
    phone: str,
    header: str,
    body: str,
    footer: str,
    buttons: list[dict],
    phone_number_id: str | None = None,
) -> httpx.Response:
    """
    Send an interactive message with quick-reply buttons.
    buttons = [{"id": "confirm_apt", "title": "✅ Confirm"}, ...]
    Maximum 3 buttons (WhatsApp limit).
    """
    pid = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "footer": {"text": footer},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]
                ]
            },
        },
    }
    return await _post(pid, payload)


async def send_template(
    phone: str,
    template_name: str,
    params: list,
    phone_number_id: str | None = None,
) -> httpx.Response:
    """
    Send a pre-approved WhatsApp template message.
    params = list of strings injected into {{1}}, {{2}}, ... placeholders.
    """
    pid = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in params],
                }
            ],
        },
    }
    return await _post(pid, payload)
