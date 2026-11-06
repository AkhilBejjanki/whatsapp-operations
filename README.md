# WhatsApp Bulk Sender

Upload a CSV/Excel of contacts, pick a Meta-approved template, send to everyone through the
official WhatsApp Cloud API, and track each message: sent, delivered, read, failed, invalid.

```
frontend/   Next.js + Tailwind (the website)
backend/    FastAPI (API + webhook) and a Celery worker (sends messages)
            PostgreSQL stores everything, Redis is the job queue
```

## Run it locally

You need Docker Desktop and Node.js 20+.

```bash
# 1. Backend: database, Redis, API (port 8000) and worker
cp .env.example .env        # then fill in SECRET_KEY, ENCRYPTION_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
docker compose up -d --build

# 2. Frontend (port 3000)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open http://localhost:3000 and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.

### Mock mode (no Meta account needed)

With `WHATSAPP_MOCK=true` in `.env`, nothing is sent to WhatsApp. Enter any IDs and token in
Settings and the app fakes Meta's responses and webhooks:

- numbers ending in `00` fail with "not on WhatsApp" (error 131026)
- numbers ending in `1` are delivered but not read
- all other numbers are delivered, then read

Set `WHATSAPP_MOCK=false` and run `docker compose up -d` to send for real.

## Connecting a real WhatsApp number (phase 1: one business)

Done in the business owner's Meta account:

1. **Create a Meta app**: https://developers.facebook.com/apps → Create app → type *Business* →
   attach it to the business's Business Portfolio → add the **WhatsApp** product.
2. **Add the phone number**: WhatsApp → API Setup → add phone number. It must not be logged in
   to the normal WhatsApp or WhatsApp Business app. Meta approves the display name.
3. **Payment method**: WhatsApp Manager → add a card. Meta bills the business per message.
4. **Permanent token**: Business Settings → Users → System users → Add (Admin) → Assign assets
   (the app, plus the WhatsApp account with full control) → Generate token with the
   `whatsapp_business_messaging` and `whatsapp_business_management` permissions and no expiry.
5. In this app's **Settings**, paste the **WhatsApp Business Account ID**, **Phone number ID**
   and the token, then click **Connect**.
6. **Webhook** (needed for delivered/read/failed statuses):
   - Put `META_APP_SECRET` (App settings → Basic) and `WEBHOOK_VERIFY_TOKEN` in `.env`.
   - Meta needs a public HTTPS URL. Locally: `ngrok http 8000`, then use
     `https://<your-ngrok-id>.ngrok-free.app/api/webhook`.
   - Meta App Dashboard → WhatsApp → Configuration → Callback URL + Verify token → Verify.
     Then under *Webhook fields*, subscribe to `messages` and `message_template_status_update`.
   - In this app's Settings, click **Subscribe webhooks**.
7. Go to **Templates → Sync from Meta**, or create a template and wait for approval.

## How sending works

1. Upload: the file is parsed and stored, and the phone and name columns are guessed.
2. Create campaign (draft): every number is converted to E.164 (`+919876543210`) using the
   default country. Invalid numbers and rows with empty variables are marked **invalid**, and
   duplicates are removed.
3. Start: a Celery task sends at `SEND_RATE_PER_SECOND`, retries rate-limit errors with
   backoff, and pauses the whole campaign on account-level errors (expired token, payment
   problem, template disabled) instead of failing every message.
4. Meta's webhooks move each message forward: accepted → sent → delivered → read, or failed
   with an error code. The dashboard explains each code in plain language.

Message statuses: `invalid` (never sent), `queued`, `accepted` (Meta took it), `sent`,
`delivered`, `read`, `failed`, `cancelled`.

## Before production

- Deploy the backend, worker, Postgres and Redis on a server (a VPS with this docker-compose,
  or Railway/Render). Deploy the frontend on Vercel and set `NEXT_PUBLIC_API_URL`.
- Put HTTPS in front of the API. The webhook URL must be HTTPS.
- Set `FRONTEND_ORIGIN` to the real frontend URL, and use strong `SECRET_KEY` / `ADMIN_PASSWORD`.
- Back up `ENCRYPTION_KEY`. Without it, saved Meta tokens can't be decrypted.
- Switch from `create_all` to Alembic migrations before changing database tables.

## Phase 2 (SaaS) roadmap

- Turn on `ALLOW_SIGNUP` and add a sign-up page. `/api/auth/register` already exists, and
  every table is already scoped by `organization_id`.
- Replace manual credential entry with Meta **Embedded Signup**. It fills the same
  `whatsapp_accounts` table.
- Get your company verified, pass App Review, and become a Meta Tech Provider.
- Add subscription billing (Razorpay), per-plan limits, team members, and an inbox for replies.
  Incoming messages already arrive on the webhook.
