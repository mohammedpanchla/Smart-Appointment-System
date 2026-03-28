# Smart Appointment System — Python Edition

One Python application. One database. Serves every clinic from a single deployment.

This replaces your 96-node n8n workflow with **~400 lines of clean, debuggable Python**.

---

## Architecture

```
Cal.com Webhook          WhatsApp Webhook
      │                        │
      ▼                        ▼
  FastAPI (webhooks.py)    FastAPI (bot.py)
      │                        │
      └──────────┬─────────────┘
                 │
         database.py  ──►  Supabase (PostgreSQL)
                 │
         whatsapp.py  ──►  Meta WhatsApp Cloud API
                 │
         scheduler.py ──►  APScheduler
                              ├── Every minute: 1-hr reminders
                              ├── Every minute: 2-hr care tips
                              ├── Every minute: No-show detection
                              └── 8:00 AM IST: Morning digest
```

---

## What it does

| Trigger | Action |
|---------|--------|
| Cal.com `BOOKING_CREATED` | Save to Supabase → Send WhatsApp confirmation + interactive buttons → Notify staff |
| Cal.com `BOOKING_CANCELLED` | Update status → Notify patient + staff |
| Cal.com `BOOKING_RESCHEDULED` | Update record → Notify patient with new buttons → Notify staff |
| WhatsApp button: **Confirm** | Mark `Confirmed` → Send confirmation message |
| WhatsApp button: **Cancel** | Mark `Cancelled` → Send cancellation message |
| WhatsApp text: `STATUS 089XXXXX` | Look up appointment → Reply with details |
| 55–65 min before appointment | Send 1-hour reminder |
| 115–125 min before appointment | Send service-specific care tips |
| 30–35 min after appointment | Detect no-show → Send template → Alert staff |
| Daily at 8:00 AM IST | Send morning schedule digest to staff |

---

## Setup

### 1. Clone & install

```bash
git clone <your-repo>
cd smart_appointment_system
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in all values
```

### 3. Set up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** and run the entire contents of `supabase_schema.sql`
3. Edit the seeded clinic row with your real clinic details
4. Copy the **Project URL** and **service_role key** into `.env`

### 4. Set up WhatsApp

1. Create a Meta App at [developers.facebook.com](https://developers.facebook.com)
2. Add the **WhatsApp** product
3. Get your **Phone Number ID** and generate a **Permanent Access Token**
4. Set up two webhooks pointing at your server:
   - `POST https://your-server.com/webhooks/whatsapp-webhook` → incoming messages
   - `POST https://your-server.com/webhooks/cal-webhook` → Cal.com events
5. Subscribe to `messages` in the WhatsApp webhook config
6. Set `WHATSAPP_VERIFY_TOKEN` to match what you enter in Meta's webhook config

### 5. Configure Cal.com

1. Go to **Settings → Webhooks** in Cal.com
2. Create a webhook pointing to: `https://your-server.com/webhooks/cal-webhook`
3. Enable events: `BOOKING_CREATED`, `BOOKING_CANCELLED`, `BOOKING_RESCHEDULED`

### 6. Create WhatsApp templates (required for no-show + review messages)

In Meta Business Manager, create these approved templates:

**`missed_appointment`** — parameters: `{{1}}` name, `{{2}}` date, `{{3}}` time, `{{4}}` service, `{{5}}` booking URL

**`visit_review_request`** — parameters: `{{1}}` name, `{{2}}` service, `{{3}}` Google review URL

### 7. Run locally

```bash
uvicorn main:app --reload --port 8000
```

### 8. Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

Set all `.env` variables in Railway's environment settings.
Your server URL will be something like `https://your-app.railway.app`.

---

## Adding a new clinic

Just insert one row into the `clinics` table:

```sql
INSERT INTO clinics (id, name, staff_phone, booking_url, google_review_url)
VALUES (
    'clinic_002',
    'Bright Smiles Dental',
    '917890123456',
    'https://cal.com/bright-smiles/dentist',
    'https://g.page/r/BRIGHT_SMILES_REVIEW'
);
```

That's it. No code changes. No new deployments.

---

## File structure

```
smart_appointment_system/
├── main.py               # FastAPI app + scheduler startup
├── config.py             # Environment variables
├── database.py           # All Supabase queries
├── whatsapp.py           # WhatsApp Cloud API wrapper
├── webhooks.py           # Cal.com event handlers
├── bot.py                # WhatsApp bot (button replies + text commands)
├── scheduler.py          # APScheduler jobs
├── supabase_schema.sql   # Run once in Supabase SQL Editor
├── requirements.txt
├── .env.example
└── README.md
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/webhooks/cal-webhook` | Cal.com events |
| `GET` | `/webhooks/whatsapp-webhook` | WhatsApp webhook verification |
| `POST` | `/webhooks/whatsapp-webhook` | Incoming WhatsApp messages |

---

## Cost at scale

| Clients | Monthly server cost |
|---------|---------------------|
| 1–20 | ~$0 (Railway free tier) |
| 20–100 | ~$5–10/month |
| 100+ | ~$20/month |

Supabase free tier: 500 MB database, 50,000 API calls/month — enough for 20+ active clinics.
