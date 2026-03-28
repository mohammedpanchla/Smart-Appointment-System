"""
bot.py — WhatsApp incoming message handler.
Handles button replies (confirm / cancel) and text commands (STATUS <ID>).

Multi-clinic: identifies which clinic received the message using
value.metadata.phone_number_id from the WhatsApp webhook payload,
then looks up the clinic record to use the correct name/booking URL.
"""
import logging

from fastapi import APIRouter, HTTPException, Request

import whatsapp
from config import settings
from database import (
    get_appointment_by_id,
    get_appointments_by_phone,
    get_clinic,
    get_clinic_by_whatsapp_phone_id,
    get_pending_appointment_by_phone,
    update_appointment,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── WhatsApp webhook verification (GET) ───────────────────────────────────────

@router.get("/whatsapp-webhook")
async def whatsapp_verify(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully.")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Webhook verification failed.")


# ── WhatsApp webhook events (POST) ────────────────────────────────────────────

@router.post("/whatsapp-webhook")
async def whatsapp_webhook(request: Request):
    body = await request.json()

    try:
        entry = body["entry"][0]
        value = entry["changes"][0]["value"]

        # Delivery / read statuses — ignore
        if "statuses" in value and "messages" not in value:
            return {"status": "ok"}

        messages = value.get("messages", [])
        if not messages:
            return {"status": "ok"}

        message = messages[0]
        from_phone: str = message["from"]
        msg_type: str = message["type"]

        # ── Multi-clinic: identify clinic from the incoming phone_number_id ────
        # Meta sends metadata.phone_number_id = the clinic's WhatsApp number ID
        # that received the message. We look up the clinic from this.
        incoming_phone_id: str = value.get("metadata", {}).get("phone_number_id", "")
        clinic = _get_clinic_for_message(incoming_phone_id)
        wa_phone_id = clinic.get("whatsapp_phone_id") or settings.WHATSAPP_PHONE_NUMBER_ID

        if msg_type == "interactive":
            button_id: str = message["interactive"]["button_reply"]["id"]
            await _handle_button(from_phone, button_id, clinic, wa_phone_id)

        elif msg_type == "text":
            text: str = message["text"]["body"].strip()
            await _handle_text(from_phone, text, clinic, wa_phone_id)

    except (KeyError, IndexError, TypeError) as exc:
        logger.warning(f"WhatsApp webhook parse error: {exc}")

    return {"status": "ok"}


def _get_clinic_for_message(phone_number_id: str) -> dict:
    """
    Look up clinic by their WhatsApp phone_number_id.
    Falls back to DEFAULT_CLINIC_ID if not found.
    """
    if phone_number_id:
        clinic = get_clinic_by_whatsapp_phone_id(phone_number_id)
        if clinic:
            return clinic
    # Fallback — useful during development / single-clinic setups
    return get_clinic(settings.DEFAULT_CLINIC_ID) or {}


# ── Button reply handler ──────────────────────────────────────────────────────

async def _handle_button(phone: str, button_id: str, clinic: dict, wa_phone_id: str):
    if button_id == "confirm_apt":
        await _confirm(phone, clinic, wa_phone_id)
    elif button_id == "cancel_apt":
        await _cancel(phone, clinic, wa_phone_id)
    else:
        logger.info(f"Unknown button_id '{button_id}' from {phone}")


async def _confirm(phone: str, clinic: dict, wa_phone_id: str):
    apt = get_pending_appointment_by_phone(phone)

    if not apt:
        confirmed = get_appointments_by_phone(phone, status_filter="Confirmed")
        if confirmed:
            latest = confirmed[0]
            await whatsapp.send_text(
                phone,
                (
                    f"✅ Your appointment (🆔 {latest['appointment_id']}) is already confirmed.\n\n"
                    f"🗓️ {latest['date']}  ⏰ {latest['time_slot']}\n"
                    f"💼 {latest['service']}\n\n"
                    f"See you soon! 😊"
                ),
                phone_number_id=wa_phone_id,
            )
        else:
            await whatsapp.send_text(
                phone,
                "❌ No pending appointment found. Please book one first.",
                phone_number_id=wa_phone_id,
            )
        return

    # Multiple pending → disambiguation
    all_pending = get_appointments_by_phone(phone, status_filter="Pending")
    if len(all_pending) > 1:
        apt_list = "\n".join(
            f"🆔 {a['appointment_id']} — {a['date']} {a['time_slot']}"
            for a in all_pending
        )
        await whatsapp.send_text(
            phone,
            f"⚠️ You have multiple pending appointments.\n\nReply with the Appointment ID to confirm:\n\n{apt_list}",
            phone_number_id=wa_phone_id,
        )
        return

    update_appointment(apt["appointment_id"], {"status": "Confirmed"})
    clinic_name = clinic.get("name", settings.DEFAULT_CLINIC_NAME)

    await whatsapp.send_text(
        phone,
        (
            f"✅ *Appointment Confirmed!*\n\n"
            f"Hello {apt['name']}, your appointment is now confirmed.\n\n"
            f"🗓️ Date: {apt['date']}\n"
            f"⏰ Time: {apt['time_slot']}\n"
            f"💼 Service: {apt['service']}\n"
            f"🆔 ID: {apt['appointment_id']}\n\n"
            f"We look forward to seeing you!\n— {clinic_name} Team 🏥"
        ),
        phone_number_id=wa_phone_id,
    )
    logger.info(f"Appointment confirmed via WhatsApp: {apt['appointment_id']}")


async def _cancel(phone: str, clinic: dict, wa_phone_id: str):
    all_pending = get_appointments_by_phone(phone, status_filter="Pending")

    if not all_pending:
        await whatsapp.send_text(
            phone,
            "❌ No pending appointment found to cancel.",
            phone_number_id=wa_phone_id,
        )
        return

    if len(all_pending) > 1:
        apt_list = "\n".join(
            f"🆔 {a['appointment_id']} — {a['date']} {a['time_slot']}"
            for a in all_pending
        )
        await whatsapp.send_text(
            phone,
            f"⚠️ You have multiple pending appointments.\n\nReply with the Appointment ID to cancel:\n\n{apt_list}",
            phone_number_id=wa_phone_id,
        )
        return

    apt = all_pending[0]
    update_appointment(apt["appointment_id"], {"status": "Cancelled"})

    clinic_name = clinic.get("name", settings.DEFAULT_CLINIC_NAME)
    booking_url = clinic.get("booking_url", settings.DEFAULT_BOOKING_URL)

    await whatsapp.send_text(
        phone,
        (
            f"❌ *Appointment Cancelled*\n\n"
            f"Your appointment (🆔 {apt['appointment_id']}) has been cancelled.\n\n"
            f"We hope to see you again soon!\n"
            f"Book a new appointment anytime:\n{booking_url}\n\n"
            f"— {clinic_name} Team 🏥"
        ),
        phone_number_id=wa_phone_id,
    )
    logger.info(f"Appointment cancelled via WhatsApp: {apt['appointment_id']}")


# ── Text message handler ──────────────────────────────────────────────────────

async def _handle_text(phone: str, text: str, clinic: dict, wa_phone_id: str):
    upper = text.upper().strip()

    if upper.startswith("STATUS"):
        parts = upper.split()
        apt_id = parts[1] if len(parts) > 1 else None
        if apt_id:
            await _lookup_and_reply(phone, apt_id, wa_phone_id)
        else:
            await whatsapp.send_text(
                phone,
                "Please provide an Appointment ID.\nExample: *STATUS 089ABC1234*",
                phone_number_id=wa_phone_id,
            )
        return

    if upper.startswith("089") and len(upper) == 10 and upper.isalnum():
        await _lookup_and_reply(phone, upper, wa_phone_id)
        return

    clinic_name = clinic.get("name", settings.DEFAULT_CLINIC_NAME)
    booking_url = clinic.get("booking_url", settings.DEFAULT_BOOKING_URL)

    await whatsapp.send_text(
        phone,
        (
            f"👋 Hello! I'm the appointment assistant for {clinic_name}.\n\n"
            f"*What I can help with:*\n"
            f"• ✅ Confirm or cancel — use the buttons we sent you\n"
            f"• 🔍 Check status — reply: *STATUS 089XXXXXXX*\n"
            f"• 📅 Book an appointment: {booking_url}\n\n"
            f"For urgent queries, please call the clinic directly. 🏥"
        ),
        phone_number_id=wa_phone_id,
    )


async def _lookup_and_reply(phone: str, apt_id: str, wa_phone_id: str):
    apt = get_appointment_by_id(apt_id)
    if apt:
        status_emoji = {
            "Pending": "⏳",
            "Confirmed": "✅",
            "Cancelled": "❌",
            "Done": "🎉",
            "No-Show": "⚠️",
        }.get(apt["status"], "📊")

        await whatsapp.send_text(
            phone,
            (
                f"📋 *Appointment Details*\n\n"
                f"🆔 ID: {apt['appointment_id']}\n"
                f"👤 Name: {apt['name']}\n"
                f"🗓️ Date: {apt['date']}\n"
                f"⏰ Time: {apt['time_slot']}\n"
                f"💼 Service: {apt['service']}\n"
                f"{status_emoji} Status: {apt['status']}"
            ),
            phone_number_id=wa_phone_id,
        )
    else:
        await whatsapp.send_text(
            phone,
            f"❌ No appointment found with ID: *{apt_id}*\n\nPlease double-check the ID and try again.",
            phone_number_id=wa_phone_id,
        )
