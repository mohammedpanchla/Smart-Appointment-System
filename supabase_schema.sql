-- ============================================================
--  Smart Appointment System — Supabase Schema
--  Run this once in the Supabase SQL Editor to create all tables.
-- ============================================================

-- ── clinics ─────────────────────────────────────────────────
-- One row per client clinic.  Add a new clinic = add a row.
CREATE TABLE IF NOT EXISTS clinics (
    id              TEXT PRIMARY KEY,          -- e.g. "clinic_001"
    name            TEXT NOT NULL,             -- "ABC Clinic"
    staff_phone     TEXT NOT NULL,             -- "919876543210"  (digits only)
    booking_url     TEXT NOT NULL,             -- "https://cal.com/…"
    google_review_url TEXT DEFAULT '',         -- "https://g.page/r/…"
    whatsapp_phone_id TEXT DEFAULT '',         -- override per-clinic if needed
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Seed your first clinic (edit these values):
INSERT INTO clinics (id, name, staff_phone, booking_url, google_review_url)
VALUES (
    'clinic_001',
    'ABC Clinic',
    '919876543210',
    'https://cal.com/your-username/dentist-appointment',
    'https://g.page/r/YOUR_GOOGLE_REVIEW_LINK'
)
ON CONFLICT (id) DO NOTHING;


-- ── appointments ────────────────────────────────────────────
-- One row per appointment across ALL clinics.
-- clinic_id separates data — Clinic A can never see Clinic B's rows.
CREATE TABLE IF NOT EXISTS appointments (
    id                   BIGSERIAL PRIMARY KEY,
    appointment_id       TEXT UNIQUE NOT NULL,   -- "089XXXXXXX"
    clinic_id            TEXT NOT NULL REFERENCES clinics(id),

    -- Patient info
    name                 TEXT NOT NULL,
    phone                TEXT NOT NULL,          -- "91XXXXXXXXXX"
    service              TEXT NOT NULL,
    date                 TEXT NOT NULL,          -- "DD-MM-YYYY" (IST)
    time_slot            TEXT NOT NULL,          -- "H:MM AM/PM" (IST)

    -- Status tracking
    status               TEXT NOT NULL DEFAULT 'Pending',
    -- Possible values: Pending | Confirmed | Cancelled | No-Show | Done

    -- Scheduler flags  (values: - | Sending | Sent | Failed)
    reminder_sent        TEXT DEFAULT '-',
    care_tips_sent       TEXT DEFAULT '-',
    review_message_sent  TEXT DEFAULT '-',
    noshow_notified      TEXT DEFAULT '-',

    -- Cal.com identifiers
    ical_uid             TEXT DEFAULT '',
    cal_booking_uid      TEXT DEFAULT '',

    -- Meta
    rescheduled          TEXT DEFAULT '-',
    created_when         TEXT DEFAULT '',        -- human-readable IST string
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

-- Auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_appointments_updated_at ON appointments;
CREATE TRIGGER trg_appointments_updated_at
    BEFORE UPDATE ON appointments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Indexes for the queries the scheduler and bot run most
CREATE INDEX IF NOT EXISTS idx_apt_phone        ON appointments (phone);
CREATE INDEX IF NOT EXISTS idx_apt_clinic_date  ON appointments (clinic_id, date);
CREATE INDEX IF NOT EXISTS idx_apt_ical_uid     ON appointments (ical_uid);
CREATE INDEX IF NOT EXISTS idx_apt_cal_uid      ON appointments (cal_booking_uid);
CREATE INDEX IF NOT EXISTS idx_apt_status       ON appointments (status);


-- ── Row-level security (optional but recommended) ────────────
-- Enable RLS so that the anon key cannot read anything.
-- The Python app uses the service_role key which bypasses RLS.

ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinics       ENABLE ROW LEVEL SECURITY;

-- No public access (service_role key always bypasses RLS)
-- Add policies here if you ever expose a dashboard with user auth.
