"""
config.py — Environment variables & settings.
All secrets live in .env. Never hard-code them here.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ─── WhatsApp ─────────────────────────────────────────────────────────────
    WHATSAPP_TOKEN: str                       # Meta permanent access token
    WHATSAPP_PHONE_NUMBER_ID: str             # Patient-facing phone number ID
    WHATSAPP_VERIFY_TOKEN: str = "my_verify_token"   # Webhook verification token

    # ─── Supabase ─────────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_KEY: str                         # service_role key (not anon)

    # ─── Default clinic (used when clinic_id is not passed by webhook) ────────
    DEFAULT_CLINIC_ID: str = "clinic_001"
    DEFAULT_CLINIC_NAME: str = "ABC Clinic"
    DEFAULT_BOOKING_URL: str = "https://cal.com/your-username/dentist-appointment"
    DEFAULT_STAFF_PHONE: str = ""             # e.g. 919876543210  (digits only, with country code)

    # ─── Cal.com ──────────────────────────────────────────────────────────────
    CAL_WEBHOOK_SECRET: str = ""              # Optional HMAC secret for signature verification

    class Config:
        env_file = ".env"


settings = Settings()
