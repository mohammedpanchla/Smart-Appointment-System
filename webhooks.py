"""
webhooks.py — Cal.com webhook handler.
Handles BOOKING_CREATED, BOOKING_CANCELLED, BOOKING_RESCHEDULED.

Multi-clinic: each clinic's Cal.com webhook URL includes ?clinic_id=clinic_001
Example: https://your-server.railway.app/webhooks/cal-webhook?clinic_id=clinic_001
"""
import logging
from datetime import datetime

import pytz
from fastapi import APIRouter, Request

import whatsapp
from config import settings
from database import (
    create_appointment,
    generate_appointment_id,
    get_appointment_by_cal_uid,
    get_appointment_by_ical,
    get_clinic,
    now_ist,
    update_appointment,
)

router = APIRouter()
logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


# ── Payload parser ────────────────────────────────────────────────────────────

def _parse_payload(body: dict) -> dict:
    """
    Normalise a Cal.com webhook body into a flat dict
    ready to be stored in Supabase.
    """
    payload = body.get("payload", {})
    attendees = payload.get("attendees", [{}])
    attendee = attendees[0] if attendees else {}

    # Phone normalisation — strip everything except digits, ensure 91 prefix
    raw_phone = attendee.get("phoneNumber", "")
    digits = "".join(filter(str.isdigit, raw_phone))
    if digits.startswith("91"):
        norm_phone = digits
    else:
        norm_phone = "91" + digits.lstrip("0")

    # Appointment time → IST
    start_raw = payload.get("startTime", "")
    try:
        start_utc = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
    except ValueError:
        start_utc = datetime.now(pytz.utc)
    start_ist = start_utc.astimezone(IST)

    date_ist = start_ist.strftime("%d-%m-%Y")
    h12 = start_ist.strftime("%-I")
    mins = start_ist.strftime("%M")
    ampm = start_ist.strftime("%p")
    time_ist = f"{h12}:{mins} {ampm}"

    # Services
    services_raw = (
        payload.get("responses", {}).get("Service", {}).get("value", "General Consultation")
    )
    if not isinstance(services_raw, list):
        services_raw = [services_raw]
    service = ", ".join(services_raw)

    n = now_ist()
    created_when = f"{n.strftime('%d-%m-%Y')} / {n.strftime('%I:%M %p')}"

    return {
        "name": attendee.get("name", ""),
        "phone": norm_phone,
        "date": date_ist,
        "time_slot": time_ist,
        "service": service,
        "ical_uid": payload.get("iCalUID", ""),
        "cal_booking_uid": payload.get("uid", ""),
        "created_when": created_when,
    }


# ── Main webhook endpoint ─────────────────────────────────────────────────────

@router.post("/cal-webhook")
async def cal_webhook(request: Request):
    body = await request.json()
    event = body.get("triggerEvent", "")

    # ── Multi-clinic: read clinic_id from query param ──────────────────────────
    # Each clinic's Cal.com webhook URL must include ?clinic_id=clinic_001
    # Example: https://your-server.railway.app/webhooks/cal-webhook?clinic_id=clinic_001
    clinic_id = request.query_params.get("clinic_id", settings.DEFAULT_CLINIC_ID)

    logger.info(f"Cal.com event: {event} | clinic: {clinic_id}")

    if event == "BOOKING_CREATED":
        await _handle_created(body, clinic_id)
    elif event == "BOOKING_CANCELLED":
        await _handle_cancelled(body)
    elif event == "BOOKING_RESCHEDULED":
        await _handle_rescheduled(body)
    else:
        logger.info(f"Ignored Cal.com event: {event}")

    return {"status": "ok"}


# ── BOOKING_CREATED ───────────────────────────────────────────────────────────

async def _handle_created(body: dict, clinic_id: str):
    data = _parse_payload(body)

    # Duplicate guard
    if get_appointment_by_ical(data["ical_uid"]):
        logger.info(f"Duplicate booking ignored: {data['ical_uid']}")
        return

    clinic = get_clinic(clinic_id) or {}
    clinic_name = clinic.get("name", settings.DEFAULT_CLINIC_NAME)
    staff_phone = clinic.get("staff_phone", settings.DEFAULT_STAFF_PHONE)
    wa_phone_id = clinic.get("whatsapp_phone_id") or settings.WHATSAPP_PHONE_NUMBER_ID

    apt_id = generate_appointment_id()

    record = {
        "appointment_id": apt_id,
        "clinic_id": clinic_id,
        "name": data["name"],
        "phone": data["phone"],
        "date": data["date"],
        "time_slot": data["time_slot"],
        "service": data["service"],
        "status": "Pending",
        "ical_uid": data["ical_uid"],
        "cal_booking_uid": data["cal_booking_uid"],
        "created_when": data["created_when"],
        "reminder_sent": "-",
        "care_tips_sent": "-",
        "review_message_sent": "-",
        "noshow_notified": "-",
        "rescheduled": "-",
    }
    create_appointment(record)

    # 1 — Confirmation text
    await whatsapp.send_text(
        data["phone"],
        (
            f"Hello {data['name']}, 👋\n\n"
            f"Thank you for choosing {clinic_name}.\n"
            f"Your appointment has been successfully booked!\n\n"
            f"📋 *Appointment Details:*\n"
            f"🆔 ID: {apt_id}\n"
            f"🗓️ Date: {data['date']}\n"
            f"⏰ Time: {data['time_slot']}\n"
            f"💼 Service: {data['service']}\n\n"
            f"Please confirm using the button below.\n"
            f"Arrive 5–10 minutes early for a smooth check-in.\n\n"
            f"— {clinic_name} Team 🏥\n"
            f"_Your Health, Our Priority._"
        ),
        phone_number_id=wa_phone_id,
    )

    # 2 — Interactive confirm / cancel buttons
    await whatsapp.send_interactive_buttons(
        phone=data["phone"],
        header="✅ Confirm Your Appointment",
        body=(
            f"Tap below to confirm or cancel:\n\n"
            f"🗓️ {data['date']}  ⏰ {data['time_slot']}\n"
            f"💼 {data['service']}"
        ),
        footer=f"{clinic_name} — Your Health, Our Priority.",
        buttons=[
            {"id": "confirm_apt", "title": "✅ Confirm Appointment"},
            {"id": "cancel_apt", "title": "❌ Cancel Appointment"},
        ],
        phone_number_id=wa_phone_id,
    )

    # 3 — Staff notification
    if staff_phone:
        await whatsapp.send_text(
            staff_phone,
            (
                f"🔔 *New Appointment Booked!*\n\n"
                f"👤 Patient: {data['name']}\n"
                f"📱 Phone: {data['phone']}\n"
                f"🗓️ Date: {data['date']}\n"
                f"⏰ Time: {data['time_slot']}\n"
                f"💼 Service: {data['service']}\n"
                f"🆔 ID: {apt_id}"
            ),
            phone_number_id=wa_phone_id,
        )

    logger.info(f"Booking created: {apt_id} — {data['name']} — {data['date']} {data['time_slot']}")


# ── BOOKING_CANCELLED ─────────────────────────────────────────────────────────

async def _handle_cancelled(body: dict):
    payload = body.get("payload", {})
    ical_uid = payload.get("iCalUID", "")
    cal_uid = payload.get("uid", "")

    apt = get_appointment_by_ical(ical_uid) or get_appointment_by_cal_uid(cal_uid)
    if not apt:
        logger.warning(f"Cancellation: appointment not found (iCal={ical_uid})")
        return

    update_appointment(apt["appointment_id"], {"status": "Cancelled"})

    clinic = get_clinic(apt.get("clinic_id", settings.DEFAULT_CLINIC_ID)) or {}
    clinic_name = clinic.get("name", settings.DEFAULT_CLINIC_NAME)
    staff_phone = clinic.get("staff_phone", settings.DEFAULT_STAFF_PHONE)
    booking_url = clinic.get("booking_url", settings.DEFAULT_BOOKING_URL)
    wa_phone_id = clinic.get("whatsapp_phone_id") or settings.WHATSAPP_PHONE_NUMBER_ID

    await whatsapp.send_text(
        apt["phone"],
        (
            f"❌ *Appointment Cancelled*\n\n"
            f"Hello {apt['name']},\n\n"
            f"Your appointment (🆔 {apt['appointment_id']}) has been cancelled.\n\n"
            f"We hope to see you again soon!\n"
            f"Book a new appointment anytime:\n{booking_url}\n\n"
            f"— {clinic_name} Team 🏥"
        ),
        phone_number_id=wa_phone_id,
    )

    if staff_phone:
        await whatsapp.send_text(
            staff_phone,
            (
                f"🚫 *Appointment Cancelled (Cal.com)*\n\n"
                f"👤 {apt['name']}\n"
                f"📱 {apt['phone']}\n"
                f"🗓️ {apt['date']}  ⏰ {apt['time_slot']}\n"
                f"💼 {apt['service']}\n"
                f"🆔 {apt['appointment_id']}"
            ),
            phone_number_id=wa_phone_id,
        )

    logger.info(f"Booking cancelled: {apt['appointment_id']}")


# ── BOOKING_RESCHEDULED ───────────────────────────────────────────────────────

async def _handle_rescheduled(body: dict):
    payload = body.get("payload", {})
    ical_uid = payload.get("iCalUID", "")
    cal_uid = payload.get("uid", "")

    old_apt = get_appointment_by_ical(ical_uid) or get_appointment_by_cal_uid(cal_uid)
    new_data = _parse_payload(body)

    clinic_id = old_apt["clinic_id"] if old_apt else settings.DEFAULT_CLINIC_ID
    clinic = get_clinic(clinic_id) or {}
    clinic_name = clinic.get("name", settings.DEFAULT_CLINIC_NAME)
    staff_phone = clinic.get("staff_phone", settings.DEFAULT_STAFF_PHONE)
    wa_phone_id = clinic.get("whatsapp_phone_id") or settings.WHATSAPP_PHONE_NUMBER_ID

    if old_apt:
        update_appointment(
            old_apt["appointment_id"],
            {
                "date": new_data["date"],
                "time_slot": new_data["time_slot"],
                "service": new_data["service"],
                "status": "Pending",
                "reminder_sent": "-",
                "care_tips_sent": "-",
                "rescheduled": "Yes",
            },
        )
        apt_id = old_apt["appointment_id"]
        patient_name = old_apt["name"]
        patient_phone = old_apt["phone"]
    else:
        apt_id = generate_appointment_id()
        patient_name = new_data["name"]
        patient_phone = new_data["phone"]
        create_appointment(
            {
                **new_data,
                "appointment_id": apt_id,
                "clinic_id": clinic_id,
                "status": "Pending",
                "rescheduled": "Yes",
                "reminder_sent": "-",
                "care_tips_sent": "-",
                "review_message_sent": "-",
                "noshow_notified": "-",
            }
        )

    await whatsapp.send_interactive_buttons(
        phone=patient_phone,
        header="🔄 Appointment Rescheduled",
        body=(
            f"Hello {patient_name}, your appointment has been rescheduled.\n\n"
            f"🗓️ New Date: {new_data['date']}\n"
            f"⏰ New Time: {new_data['time_slot']}\n"
            f"💼 Service: {new_data['service']}\n"
            f"🆔 ID: {apt_id}"
        ),
        footer=f"{clinic_name} — Your Health, Our Priority.",
        buttons=[
            {"id": "confirm_apt", "title": "✅ Confirm Appointment"},
            {"id": "cancel_apt", "title": "❌ Cancel Appointment"},
        ],
        phone_number_id=wa_phone_id,
    )

    if staff_phone:
        await whatsapp.send_text(
            staff_phone,
            (
                f"🔄 *Appointment Rescheduled*\n\n"
                f"👤 {patient_name}\n"
                f"📱 {patient_phone}\n"
                f"🗓️ New Date: {new_data['date']}  ⏰ {new_data['time_slot']}\n"
                f"💼 {new_data['service']}\n"
                f"🆔 {apt_id}"
            ),
            phone_number_id=wa_phone_id,
        )

    logger.info(f"Booking rescheduled: {apt_id} → {new_data['date']} {new_data['time_slot']}")
