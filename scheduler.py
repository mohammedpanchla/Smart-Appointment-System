"""
scheduler.py — All timed jobs.
Four jobs total:
  1. Every minute — 1-hour appointment reminders
  2. Every minute — 2-hour care tips
  3. Every minute — No-show detection (30–35 min after appointment)
  4. Daily 8:00 AM IST — Morning digest to staff
"""
import logging
import re
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import whatsapp
from config import settings
from database import (
    get_all_clinics,
    get_appointments_for_noshow_check,
    get_appointments_needing_care_tips,
    get_appointments_needing_reminder,
    get_clinic,
    get_todays_appointments,
    now_ist,
    update_appointment,
)

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


# ── Shared utilities ──────────────────────────────────────────────────────────

def _parse_apt_datetime(date_str: str, time_str: str) -> datetime | None:
    """Parse DD-MM-YYYY + H:MM AM/PM → timezone-aware IST datetime."""
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %I:%M %p")
        return IST.localize(dt)
    except Exception as exc:
        logger.error(f"Cannot parse '{date_str} {time_str}': {exc}")
        return None


def _time_to_minutes(t: str) -> int:
    """'3:45 PM' → total minutes since midnight (for sorting)."""
    m = re.match(r"(\d+):(\d+)\s*(AM|PM)", t or "", re.IGNORECASE)
    if not m:
        return 0
    h, mn, ap = int(m[1]), int(m[2]), m[3].upper()
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return h * 60 + mn


def _clinic_defaults(clinic: dict) -> tuple[str, str, str]:
    """Return (clinic_name, staff_phone, booking_url) with fallbacks."""
    name = clinic.get("name", settings.DEFAULT_CLINIC_NAME)
    phone = clinic.get("staff_phone", settings.DEFAULT_STAFF_PHONE)
    url = clinic.get("booking_url", settings.DEFAULT_BOOKING_URL)
    return name, phone, url


def _build_care_tips(name: str, service: str, clinic_name: str) -> str:
    svc = service.lower()
    if "cleaning" in svc:
        tips = (
            "🪥 *Pre-visit tips for Tooth Cleaning:*\n\n"
            "• Brush and floss gently before arriving\n"
            "• Avoid eating 30 minutes beforehand\n"
            "• Bring previous dental records if you have them"
        )
    elif "consultation" in svc:
        tips = (
            "💬 *Pre-visit tips for your Consultation:*\n\n"
            "• Note down any dental pain or concerns\n"
            "• List any medications you are currently taking\n"
            "• Bring previous dental X-rays if available"
        )
    elif "alignment" in svc or "braces" in svc:
        tips = (
            "🦷 *Pre-visit tips for Tooth Alignment:*\n\n"
            "• Brush and floss thoroughly before your visit\n"
            "• Avoid hard or sticky foods today\n"
            "• Bring your current aligners or retainer if any"
        )
    elif "whitening" in svc:
        tips = (
            "✨ *Pre-visit tips for Tooth Whitening:*\n\n"
            "• Avoid dark drinks (coffee, tea) for 24 hours before\n"
            "• Brush gently — do not bleach at home today\n"
            "• Some sensitivity is normal after treatment"
        )
    else:
        tips = (
            "🏥 *Pre-appointment reminder:*\n\n"
            "• Please arrive 5–10 minutes early\n"
            "• Bring any previous dental records if available\n"
            "• Stay hydrated!"
        )
    return (
        f"⏰ *Your appointment is in about 2 hours, {name}!*\n\n"
        f"{tips}\n\n"
        f"See you soon at {clinic_name}! 😊\n"
        f"— {clinic_name} Team 🏥"
    )


# ── Job 1 — 1-hour reminder ───────────────────────────────────────────────────

async def job_reminders():
    appointments = get_appointments_needing_reminder()
    now = now_ist()

    for apt in appointments:
        apt_time = _parse_apt_datetime(apt["date"], apt["time_slot"])
        if not apt_time:
            continue
        diff_min = (apt_time - now).total_seconds() / 60
        if not (55 <= diff_min <= 65):
            continue

        # Optimistic lock to prevent double-send
        update_appointment(apt["appointment_id"], {"reminder_sent": "Sending"})

        clinic = get_clinic(apt.get("clinic_id", settings.DEFAULT_CLINIC_ID)) or {}
        clinic_name, _, _ = _clinic_defaults(clinic)

        msg = (
            f"⏰ *Appointment Reminder*\n\n"
            f"Hello {apt['name']}, your appointment is in *1 hour!*\n\n"
            f"🗓️ Date: {apt['date']}\n"
            f"⏰ Time: {apt['time_slot']}\n"
            f"💼 Service: {apt['service']}\n"
            f"🆔 ID: {apt['appointment_id']}\n\n"
            f"Please arrive 5–10 minutes early.\n"
            f"— {clinic_name} Team 🏥"
        )
        resp = await whatsapp.send_text(apt["phone"], msg)
        status = "Sent" if resp.status_code in (200, 201) else "Failed"
        update_appointment(apt["appointment_id"], {"reminder_sent": status})
        logger.info(f"[Reminder] {apt['appointment_id']} → {status}")


# ── Job 2 — 2-hour care tips ──────────────────────────────────────────────────

async def job_care_tips():
    appointments = get_appointments_needing_care_tips()
    now = now_ist()

    for apt in appointments:
        apt_time = _parse_apt_datetime(apt["date"], apt["time_slot"])
        if not apt_time:
            continue
        diff_min = (apt_time - now).total_seconds() / 60
        if not (115 <= diff_min <= 125):
            continue

        update_appointment(apt["appointment_id"], {"care_tips_sent": "Sending"})

        clinic = get_clinic(apt.get("clinic_id", settings.DEFAULT_CLINIC_ID)) or {}
        clinic_name, _, _ = _clinic_defaults(clinic)

        msg = _build_care_tips(apt["name"], apt["service"], clinic_name)
        resp = await whatsapp.send_text(apt["phone"], msg)
        status = "Sent" if resp.status_code in (200, 201) else "Failed"
        update_appointment(apt["appointment_id"], {"care_tips_sent": status})
        logger.info(f"[Care Tips] {apt['appointment_id']} → {status}")


# ── Job 3 — No-show detection ─────────────────────────────────────────────────

async def job_noshow():
    appointments = get_appointments_for_noshow_check()
    now = now_ist()

    for apt in appointments:
        apt_time = _parse_apt_datetime(apt["date"], apt["time_slot"])
        if not apt_time:
            continue
        diff_min = (now - apt_time).total_seconds() / 60
        if not (30 <= diff_min <= 35):
            continue

        update_appointment(apt["appointment_id"], {"noshow_notified": "Sending"})

        clinic = get_clinic(apt.get("clinic_id", settings.DEFAULT_CLINIC_ID)) or {}
        clinic_name, staff_phone, booking_url = _clinic_defaults(clinic)

        # Template message to patient (pre-approved template required in Meta)
        await whatsapp.send_template(
            phone=apt["phone"],
            template_name="missed_appointment",
            params=[
                apt["name"],
                apt["date"],
                apt["time_slot"],
                apt["service"],
                booking_url,
            ],
        )

        # Staff alert
        if staff_phone:
            await whatsapp.send_text(
                staff_phone,
                (
                    f"⚠️ *No-Show Alert*\n\n"
                    f"👤 {apt['name']} — {apt['phone']}\n"
                    f"🗓️ {apt['date']}  ⏰ {apt['time_slot']}\n"
                    f"💼 {apt['service']}\n"
                    f"🆔 {apt['appointment_id']}"
                ),
            )

        update_appointment(
            apt["appointment_id"],
            {"status": "No-Show", "noshow_notified": "Sent"},
        )
        logger.info(f"[No-Show] {apt['appointment_id']} marked.")


# ── Job 4 — Morning digest (8 AM IST) ────────────────────────────────────────

async def job_morning_digest():
    clinics = get_all_clinics()

    for clinic in clinics:
        staff_phone = clinic.get("staff_phone", "")
        if not staff_phone:
            continue

        appointments = get_todays_appointments(clinic["id"])
        if not appointments:
            continue

        today = now_ist().strftime("%d-%m-%Y")
        total = len(appointments)
        confirmed = sum(1 for a in appointments if a["status"] == "Confirmed")
        pending = sum(1 for a in appointments if a["status"] == "Pending")
        cancelled = sum(1 for a in appointments if a["status"] == "Cancelled")

        active = sorted(
            [a for a in appointments if a["status"] not in ("Cancelled",)],
            key=lambda a: _time_to_minutes(a["time_slot"]),
        )
        apt_list = "\n".join(
            f"{i + 1}. {a['time_slot']} — {a['name']} ({a['service']})"
            for i, a in enumerate(active)
        ) or "No active appointments today."

        msg = (
            f"🌅 *Good morning! Today's Schedule — {today}*\n\n"
            f"📊 Overview:\n"
            f"• Total: {total} | ✅ Confirmed: {confirmed} | ⏳ Pending: {pending} | ❌ Cancelled: {cancelled}\n\n"
            f"📋 *Appointment List:*\n{apt_list}\n\n"
            f"Have a great day! — {clinic['name']} System 🏥"
        )
        await whatsapp.send_text(staff_phone, msg)
        logger.info(f"[Digest] Sent for clinic {clinic['id']}")


# ── Scheduler factory ─────────────────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=IST)

    scheduler.add_job(job_reminders, "interval", minutes=1, id="reminders", max_instances=1)
    scheduler.add_job(job_care_tips, "interval", minutes=1, id="care_tips", max_instances=1)
    scheduler.add_job(job_noshow, "interval", minutes=1, id="noshow", max_instances=1)
    scheduler.add_job(
        job_morning_digest,
        CronTrigger(hour=8, minute=0, timezone=IST),
        id="morning_digest",
        max_instances=1,
    )

    return scheduler
