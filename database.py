"""
database.py — All Supabase interactions.
One function per operation. Nothing else.
"""
import random
import string
import logging
from datetime import datetime

import pytz
from supabase import create_client, Client

from config import settings

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# ── Client (module-level singleton) ──────────────────────────────────────────
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_ist() -> datetime:
    return datetime.now(IST)


def generate_appointment_id() -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=7))
    return f"089{suffix}"


# ── Clinic helpers ────────────────────────────────────────────────────────────

def get_clinic(clinic_id: str) -> dict | None:
    try:
        result = supabase.table("clinics").select("*").eq("id", clinic_id).single().execute()
        return result.data
    except Exception as e:
        logger.warning(f"get_clinic({clinic_id}) failed: {e}")
        return None


def get_clinic_by_whatsapp_phone_id(phone_number_id: str) -> dict | None:
    """
    Look up a clinic by their WhatsApp phone_number_id.
    Called by bot.py when an incoming message arrives — the metadata.phone_number_id
    in the WhatsApp webhook payload identifies which clinic's number received the message.
    """
    try:
        result = (
            supabase.table("clinics")
            .select("*")
            .eq("whatsapp_phone_id", phone_number_id)
            .single()
            .execute()
        )
        return result.data
    except Exception as e:
        logger.warning(f"get_clinic_by_whatsapp_phone_id({phone_number_id}) failed: {e}")
        return None


def get_all_clinics() -> list[dict]:
    result = supabase.table("clinics").select("*").execute()
    return result.data or []


# ── Appointment CRUD ──────────────────────────────────────────────────────────

def create_appointment(data: dict) -> dict | None:
    result = supabase.table("appointments").insert(data).execute()
    return result.data[0] if result.data else None


def get_appointment_by_ical(ical_uid: str) -> dict | None:
    result = supabase.table("appointments").select("*").eq("ical_uid", ical_uid).execute()
    return result.data[0] if result.data else None


def get_appointment_by_cal_uid(cal_uid: str) -> dict | None:
    result = supabase.table("appointments").select("*").eq("cal_booking_uid", cal_uid).execute()
    return result.data[0] if result.data else None


def get_appointment_by_id(appointment_id: str) -> dict | None:
    result = supabase.table("appointments").select("*").eq("appointment_id", appointment_id).execute()
    return result.data[0] if result.data else None


def get_appointments_by_phone(phone: str, status_filter: str | None = None) -> list[dict]:
    q = supabase.table("appointments").select("*").eq("phone", phone)
    if status_filter:
        q = q.eq("status", status_filter)
    result = q.order("created_at", desc=True).execute()
    return result.data or []


def get_pending_appointment_by_phone(phone: str) -> dict | None:
    result = (
        supabase.table("appointments")
        .select("*")
        .eq("phone", phone)
        .eq("status", "Pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def update_appointment(appointment_id: str, updates: dict) -> dict | None:
    result = (
        supabase.table("appointments")
        .update(updates)
        .eq("appointment_id", appointment_id)
        .execute()
    )
    return result.data[0] if result.data else None


# ── Scheduler queries ─────────────────────────────────────────────────────────

def _today_str() -> str:
    return now_ist().strftime("%d-%m-%Y")


def get_todays_appointments(clinic_id: str | None = None) -> list[dict]:
    q = supabase.table("appointments").select("*").eq("date", _today_str())
    if clinic_id:
        q = q.eq("clinic_id", clinic_id)
    return q.execute().data or []


def get_appointments_needing_reminder(clinic_id: str | None = None) -> list[dict]:
    q = (
        supabase.table("appointments")
        .select("*")
        .in_("status", ["Pending", "Confirmed"])
        .not_.in_("reminder_sent", ["Sending", "Sent"])
        .eq("date", _today_str())
    )
    if clinic_id:
        q = q.eq("clinic_id", clinic_id)
    return q.execute().data or []


def get_appointments_needing_care_tips(clinic_id: str | None = None) -> list[dict]:
    q = (
        supabase.table("appointments")
        .select("*")
        .in_("status", ["Pending", "Confirmed"])
        .not_.in_("care_tips_sent", ["Sending", "Sent"])
        .eq("date", _today_str())
    )
    if clinic_id:
        q = q.eq("clinic_id", clinic_id)
    return q.execute().data or []


def get_appointments_for_noshow_check(clinic_id: str | None = None) -> list[dict]:
    q = (
        supabase.table("appointments")
        .select("*")
        .in_("status", ["Pending", "Confirmed"])
        .not_.in_("noshow_notified", ["Sending", "Sent"])
        .eq("date", _today_str())
    )
    if clinic_id:
        q = q.eq("clinic_id", clinic_id)
    return q.execute().data or []
