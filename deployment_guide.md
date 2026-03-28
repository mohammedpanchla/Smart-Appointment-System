# Smart Appointment System — Complete Deployment Guide
## Python Edition · Multi-Clinic · Production Ready

---

## PART A — ONE-TIME SERVER SETUP
*Do this once. Never again. All clinics share this same server.*

---

### A1 — Create your Supabase database (10 minutes)

1. Go to **supabase.com** → Sign up free → Create new project
2. Give it a name like `smart-appointment-system`
3. Choose region: **South Asia (Singapore)** — lowest latency for India/UAE
4. Wait 2 minutes for the project to spin up

Once inside your Supabase project:
5. Click **SQL Editor** in the left sidebar
6. Paste and run the entire contents of `supabase_schema.sql`
7. You will see: `Success. No rows returned.` — that means it worked

Now get your credentials:
8. Go to **Settings → API**
9. Copy these two values and save them somewhere safe:
   - **Project URL** — looks like `https://abcdefgh.supabase.co`
   - **service_role key** (NOT the anon key) — a long JWT token starting with `eyJ...`

---

### A2 — Deploy to Railway (15 minutes)

1. Go to **railway.app** → Sign up with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Push all your Python files to a GitHub repo first (create one at github.com if you don't have one)
4. Select that repo in Railway
5. Railway will detect it's a Python project automatically

Once deployed:
6. Go to your project in Railway → **Variables** tab
7. Add these environment variables one by one:

```
WHATSAPP_TOKEN         = [your Meta permanent access token]
WHATSAPP_PHONE_NUMBER_ID = [your first clinic's phone number ID from Meta]
WHATSAPP_VERIFY_TOKEN  = dental2024
SUPABASE_URL           = [your Supabase project URL]
SUPABASE_KEY           = [your Supabase service_role key]
DEFAULT_CLINIC_ID      = clinic_001
DEFAULT_CLINIC_NAME    = ABC Clinic
DEFAULT_BOOKING_URL    = https://cal.com/your-link
DEFAULT_STAFF_PHONE    = 919876543210
```

8. Go to **Settings → Networking → Generate Domain**
9. Copy your Railway URL — it looks like `https://your-app-name.railway.app`

This URL is your server. Every clinic's webhooks point here.

---

### A3 — Connect WhatsApp webhook to your server (5 minutes)

In Meta Developer Console (developers.facebook.com):
1. Open your app → WhatsApp → Configuration
2. **Webhook URL:** `https://your-app-name.railway.app/webhooks/whatsapp-webhook`
3. **Verify Token:** `dental2024` (must match WHATSAPP_VERIFY_TOKEN)
4. Click **Verify and Save**
5. Under Webhook Fields → click **Subscribe** next to `messages`

Test it: send a WhatsApp message to your clinic number. Check Railway logs — you should see the webhook arrive.

---

## PART B — PER-CLINIC ONBOARDING
*Do this for every new clinic. Takes 30–60 minutes once you know the process.*

---

### What you need FROM the client before you start

Send them this checklist:

> "To set up your system, I need 3 things from you:
>
> 1. **A new SIM card** — buy any Jio/Airtel SIM that has never been used on WhatsApp before. Send me the number once it's active.
>
> 2. **Meta Business Manager verification** — go to business.facebook.com, create a business account using your personal Facebook login, and upload your GST certificate or clinic registration document for verification. I'll guide you through this step by step.
>
> 3. **Clinic information:**
>    - Full clinic name (exactly as you want it in messages)
>    - List of services (e.g. Tooth Cleaning, Consultation, Whitening, Alignment)
>    - Working days and hours
>    - Duration per appointment type (e.g. cleaning = 45 min)
>    - Your personal WhatsApp number (for staff alerts)
>    - Your Google Business review link (open Google Maps → search your clinic → click Write a review → copy that URL)"

---

### B1 — Set up their Meta / WhatsApp API (takes 3–7 days including approvals)

**Day 1: Start this immediately — it's the longest wait**

After they complete Meta Business Manager verification:

1. Go to **developers.facebook.com** → My Apps → Create App → Business type
2. Connect it to their Meta Business Manager (they need to add you as Admin in Business Manager → Settings → People first)
3. Add **WhatsApp** as a product
4. Go to **WhatsApp → API Setup**
5. Click **Add Phone Number** → enter their new SIM number → verify via OTP
6. Copy the **Phone Number ID** (15-digit number) — save this
7. Go to **Business Manager → System Users → Add** → name it `automation` → role: Admin
8. Click Add Assets → WhatsApp Account → give Full Control
9. Click **Generate Token** → select your app → permissions: `whatsapp_business_messaging` + `whatsapp_business_management` → expiry: **Never**
10. Copy the **permanent access token** — save this

**Day 1: Submit WhatsApp message templates**

In Meta Business Manager → WhatsApp → Message Templates → Create:

Template 1 — `missed_appointment`
```
Category: UTILITY
Body:
😔 We missed you today, {{1}}!

🗓️ Missed: {{2}} at {{3}}
💼 Service: {{4}}

No worries — life happens! Book again anytime:
👉 {{5}}

— [Clinic Name] Team 🏥
```

Template 2 — `visit_review_request`
```
Category: UTILITY
Body:
🙏 Thank you {{1}} for visiting [Clinic Name] today!

💼 Service: {{2}}

If you enjoyed your visit, a quick Google review means the world to us:
⭐ {{3}}

Thank you for choosing us! 😊
— [Clinic Name] Team 🏥
```

Submit both. Approval takes 24–48 hours. You get an email when approved.

**Day 1: Apply for Standard Access**

In your Meta app → WhatsApp → API Setup → scroll to **Production Access** → click Apply. This is what lets you message real patients (not just test numbers). Approves in 24–48 hours once your business is verified.

**Total wait: 3–5 days if everything goes smoothly.**

---

### B2 — Create their Gmail and Cal.com accounts (30 minutes)

You do this yourself. No load on the client.

**Gmail:**
1. Go to gmail.com → Create account
2. Name it: `[clinicname].system@gmail.com` (e.g. `brightsmiles.system@gmail.com`)
3. Save the password — you'll need it for Cal.com and Supabase access

**Cal.com:**
1. Go to cal.com → Sign up with that new Gmail
2. Go to **Settings → Profile** → set clinic name and photo
3. Go to **Event Types** → Create one event type per service:
   - Title: exactly as the clinic wants it
   - Duration: as the clinic specified
   - Location: clinic address
   - Require phone number: YES (add a custom question asking for phone)
4. Go to **Availability** → set the clinic's working hours and days
5. Copy the booking link — looks like `cal.com/[username]/dentist-appointment`

**Add Cal.com webhook:**
6. Go to **Settings → Developer → Webhooks** → Add Webhook
7. URL: `https://your-app-name.railway.app/webhooks/cal-webhook?clinic_id=clinic_002`
   *(Replace `clinic_002` with this clinic's unique ID — you choose this)*
8. Enable: BOOKING_CREATED, BOOKING_CANCELLED, BOOKING_RESCHEDULED
9. Save

---

### B3 — Add the clinic to your Supabase database (5 minutes)

Once you have their WhatsApp Phone Number ID and the permanent token is ready:

1. Go to your Supabase project → **SQL Editor**
2. Run this query (fill in the real values):

```sql
INSERT INTO clinics (
    id,
    name,
    staff_phone,
    booking_url,
    google_review_url,
    whatsapp_phone_id
)
VALUES (
    'clinic_002',
    'Bright Smiles Dental',
    '919876543210',
    'https://cal.com/brightsmiles/dentist-appointment',
    'https://g.page/r/BRIGHT_SMILES_REVIEW_LINK',
    '917890123456789'
);
```

Replace:
- `clinic_002` → a unique ID you pick (clinic_001, clinic_002, clinic_003...)
- `Bright Smiles Dental` → exact clinic name
- `919876543210` → owner's personal WhatsApp (digits only, with country code, no +)
- Cal.com booking link → their actual link
- Google review URL → from their Google Business listing
- `917890123456789` → their Meta Phone Number ID (the 15-digit number from Step B1)

**That's it. No code change. No redeployment. The server automatically starts serving this clinic.**

---

### B4 — Add their WhatsApp token to your server (2 minutes)

Each clinic has their own permanent WhatsApp token. You need to handle this.

**Option A (simple — recommended for up to 5 clients):**
The code uses the `whatsapp_phone_id` from the clinic row to route messages to the right number. But outbound API calls still use the token from your `.env`. For this to work, all your clients' WhatsApp numbers must be under the **same Meta app** — meaning you add each clinic's phone number to your one Meta Developer App.

This is the recommended approach. You create one Meta Developer App, and add each clinic's phone number as a new phone number in that app. They each get their own Phone Number ID but all share one access token.

**Option B (advanced — for 10+ clients):**
Add a `whatsapp_token` column to the clinics table. Store each clinic's token there. Update `whatsapp.py` to read the token from the clinic record instead of from settings. This is cleaner at scale but more setup per client.

For your first few clients: use Option A. Add all phone numbers to your single Meta Developer App.

---

### B5 — Test everything (20 minutes — do not skip)

Run these 5 tests before telling the client you're live:

**Test 1 — New booking**
Book a test appointment on their Cal.com link using your own phone number.
Check:
- ✅ New row in Supabase → appointments table (check in Supabase Table Editor)
- ✅ WhatsApp confirmation received on your phone
- ✅ Interactive Confirm/Cancel buttons arrived
- ✅ Staff notification received on the staff number
Tap Confirm → check status changed to Confirmed in Supabase.

**Test 2 — Reminder**
In Supabase Table Editor: find your test row. Change `date` to today, `time_slot` to 1 hour from now (format: `3:30 PM`), `reminder_sent` back to `-`.
Wait up to 2 minutes.
- ✅ Reminder WhatsApp received
- ✅ `reminder_sent` changed to `Sent` in Supabase

**Test 3 — Cancel via WhatsApp**
Change the row status back to Pending in Supabase.
Message the clinic's WhatsApp number: tap Cancel from the buttons or type `STATUS 089XXXXXXX`.
- ✅ Status changes to Cancelled in Supabase
- ✅ Cancellation message received

**Test 4 — No-show**
Set `status` = Confirmed, `noshow_notified` = `-`, `time_slot` to 32 minutes ago.
Wait up to 2 minutes.
- ✅ No-show WhatsApp received on your phone
- ✅ Staff no-show alert received
- ✅ Status changed to No-Show, noshow_notified = Sent
- ✅ Does NOT fire again (wait 5 more minutes — confirm)

**Test 5 — Morning digest**
In Railway: open your project → click on your service → open a shell → run:
```
python3 -c "import asyncio; from scheduler import job_morning_digest; asyncio.run(job_morning_digest())"
```
- ✅ Morning digest WhatsApp received on staff number with today's appointments listed

All 5 pass? Go live.

---

### B6 — Staff training (30-minute call)

Call the clinic's receptionist. Cover three things only:

**Thing 1 — Marking appointments Done**
Show them Supabase Table Editor (or share a simplified Google Sheet view if they find Supabase intimidating). When a patient finishes their appointment: find the row → change Status from Confirmed to Done. That triggers the review request automatically.

**Thing 2 — What they receive every morning**
Show them a sample morning digest message. Tell them: "At 8 AM every morning, you receive the full day's schedule on WhatsApp. No need to open anything."

**Thing 3 — What NOT to do**
Never delete rows from the database. If an appointment needs removing, change Status to Cancelled.

Send them this after the call on WhatsApp:
> "Your setup is complete! Quick reference:
> 📋 After each patient leaves → change Status to *Done* in the table
> 🌅 Every morning at 8 AM → full schedule arrives on WhatsApp
> ❓ Any questions → message me at [your number]
> ✅ You're live!"

---

### B7 — Go live

Tell the client:
> "Everything is tested and live. Here's your booking link to share everywhere:
> 📅 [Cal.com link]
>
> Share it on:
> • Instagram bio
> • Google Business listing
> • WhatsApp Status
>
> Patients who book will immediately receive a WhatsApp confirmation, care tips 2 hours before, and a reminder 1 hour before — all automatic."

---

## PART C — WHAT CHANGED FROM N8N (USER PERSPECTIVE)

The patient and clinic experience is **identical**. Here is what changed under the hood, and what did not change at all.

---

### What stayed exactly the same for patients

Every message the patient receives — booking confirmation, confirm/cancel buttons, care tips, reminder, no-show message, review request — is word-for-word identical to the n8n version.

The timing is identical: confirmation fires the moment they book, care tips 2 hours before, reminder 1 hour before.

The WhatsApp bot behaviour is identical: STATUS command, appointment ID lookup, confirmation and cancellation buttons.

---

### What stayed the same for the clinic owner

Morning digest at 8 AM — same format.
Staff new booking notification — same.
Staff cancellation / reschedule alerts — same.

---

### What actually changed (only relevant to you, the developer)

| Was | Now |
|-----|-----|
| 96 n8n nodes per client | 1 Python server, all clients |
| Google Sheets as database | Supabase (PostgreSQL) |
| n8n credentials panel | `.env` file + Railway environment variables |
| n8n Executions tab for debugging | Railway logs (structured, searchable) |
| Import JSON for each client | Insert one SQL row for each client |
| Adding client = 30 min of n8n config | Adding client = 5 min SQL insert |
| Timezone bugs | Fixed — IST handled explicitly everywhere |
| No-show fires 5x | Fixed — Sending/Sent lock prevents duplicates |
| Reschedule link was broken | Fixed — uses Cal Booking UID |

---

## PART D — ADDING CLINIC #3, #4, #5...

Every new clinic after your first is just this:

1. Add their phone number to your Meta Developer App → get their Phone Number ID
2. Submit their WhatsApp templates (same 2 templates, just update the clinic name)
3. Create their Gmail + Cal.com account
4. Set Cal.com webhook URL with their `?clinic_id=clinic_003`
5. Insert one row into the `clinics` Supabase table
6. Run your 5 tests
7. Train staff (30 min)
8. Go live

**No code changes. No redeployment. Ever.**

---

## PART E — MONITORING & MAINTENANCE

**Check weekly (5 minutes):**
- Open Railway → your service → Logs tab
- Filter for `ERROR` — if you see any, read the error and fix it
- Open Supabase → Table Editor → appointments — scan for any rows stuck on `reminder_sent = Sending` (means WhatsApp failed mid-send) — manually reset to `-` so they retry

**Common issues and fixes:**

| Problem | Cause | Fix |
|---------|-------|-----|
| WhatsApp messages not arriving | Token expired or wrong Phone Number ID | Check Railway logs for HTTP 401 errors. Regenerate permanent token in Meta |
| Reminders not firing | Time format mismatch in database | Check the `time_slot` column — must be format `3:30 PM` (no leading zero, space before AM/PM) |
| Cal.com webhooks not arriving | Webhook URL wrong or Railway app restarted | Re-verify webhook in Cal.com → Settings → Webhooks |
| No-show firing on wrong appointments | Date column format wrong | Must be `DD-MM-YYYY` exactly |
| Morning digest sending at wrong time | Server timezone | Railway servers run UTC. The scheduler is set to fire at 8 AM IST (2:30 AM UTC). Verify with Railway logs |

---

## Quick Reference — Per-Clinic Checklist

```
BEFORE YOU START
[ ] Client provided new SIM number
[ ] Meta Business Manager verified (client did this)
[ ] Clinic information received (name, services, hours, review link, staff WhatsApp)

META / WHATSAPP (start Day 1 — takes 3–5 days)
[ ] Developer App created, client's phone number added
[ ] Phone Number ID saved
[ ] Permanent access token generated and saved
[ ] Template 1 (missed_appointment) submitted
[ ] Template 2 (visit_review_request) submitted
[ ] Templates approved (check email)
[ ] Standard access approved

YOUR SETUP (2–3 hours your time)
[ ] Gmail created — clinicname.system@gmail.com
[ ] Cal.com created with all services, hours, availability
[ ] Cal.com webhook URL set with correct clinic_id param
[ ] Supabase row inserted with all clinic details including whatsapp_phone_id
[ ] Phone number added to your Meta Developer App

TESTING
[ ] Test 1: New booking ✅
[ ] Test 2: Reminder ✅
[ ] Test 3: Cancel ✅
[ ] Test 4: No-show ✅
[ ] Test 5: Morning digest ✅

GO-LIVE
[ ] Staff training call done (30 min)
[ ] Reference message sent to receptionist
[ ] Booking link shared with clinic owner
[ ] First monthly payment scheduled (30 days from today)
```
