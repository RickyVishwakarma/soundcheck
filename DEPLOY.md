# Deploying SoundCheck

Two pieces: the **API** (FastAPI, wraps the Python engine) and the **dashboard**
(Next.js). Both deploy from this repo with no CLI — import from GitHub and go.

Deploy the API first; the dashboard needs its URL at build time.

---

## 1. API → Render

1. [render.com](https://render.com) → **New** → **Blueprint**
2. Connect this repo and apply — [`render.yaml`](render.yaml) supplies the
   runtime, build command, start command and health check, so there are no
   fields to fill in.
3. Wait for the first deploy, then copy the service URL
   (`https://soundcheck-api-XXXX.onrender.com`).
4. Sanity check: `curl <that-url>/api/health` → `{"ok":true,"version":"0.4.0"}`
5. In the service's **Environment** tab, set `CLERK_PUBLISHABLE_KEY` to the same
   `pk_…` key the dashboard uses.

**Why the backend needs a Clerk key.** Clerk owns sign-in on the frontend and
issues session tokens; the API only *verifies* them, and it finds Clerk's
public keys (JWKS) by decoding the publishable key. Without it the API can't
verify anyone and every signed-in request gets a 401 — the public demo still
works, but accounts don't. It is a *publishable* key, not a secret; the Clerk
secret key never goes near the backend.

Check it took effect: `curl <that-url>/api/auth/me` →
`{"authenticated":false,...,"clerk_configured":true}`.

Notes on the free plan:

- **It sleeps after ~15 minutes idle** and takes up to a minute to wake. The
  dashboard expects this and shows a "waking the API…" state rather than an
  error — that is why the page fetches client-side instead of in a server
  component (a serverless render would time out first).
- **Storage is ephemeral.** Run history lives in SQLite on local disk, so a
  restart clears it. Fine for a demo; attach a persistent disk (paid) or swap
  `server/store.py` for Postgres if you need it to stick.

## 2. Dashboard → Vercel

1. [vercel.com/new](https://vercel.com/new) → import this repo
2. **Root Directory: `dashboard`** — the repo root is a Python project, so this
   is required, not optional.
3. Add three environment variables:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | the Render URL from step 1, no trailing slash |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_…` from `dashboard/.env.local` |
   | `CLERK_SECRET_KEY` | `sk_…` from `dashboard/.env.local` |

4. Deploy.

> `NEXT_PUBLIC_*` variables are inlined **at build time**, not read at runtime.
> Changing the API URL or publishable key later needs a redeploy, not just an
> edit. `CLERK_SECRET_KEY` is server-side and must never be prefixed
> `NEXT_PUBLIC_` — that would ship it to every browser.

### About Clerk keys

`dashboard/.env.local` holds **development** keys (`pk_test_…` / `sk_test_…`).
They work on a deployed URL, but Clerk rate-limits development instances and
shows a "development keys" banner — fine for a demo or a portfolio link.

For a real production deployment, create a **production instance** in the
[Clerk dashboard](https://dashboard.clerk.com/), which requires a domain you
control (Clerk asks for DNS records; a `*.vercel.app` subdomain won't do). You
then swap in the `pk_live_…` / `sk_live_…` keys on both Vercel *and* Render.

## 3. Verify

1. Open the Vercel URL — the **landing page** should render without signing in.
2. Click **Get started** and create an account through Clerk.
3. You should land on `/dashboard`. Click **Run test** → a run page appears,
   polls, and settles on a verdict.
4. Tick **Simulate a degraded config**, run again — the gate should fail on
   `ttfa_ms`.
5. Sign out and visit `/dashboard` directly — it must redirect you to sign-in.

Step 3 needs no ElevenLabs key: it drives the built-in deterministic mock agent.
Testing a **real** agent is opt-in per run, and those credentials are used for
that request only — never written to the database or the logs.

**If signing in works but the dashboard shows no data**, the API is missing
`CLERK_PUBLISHABLE_KEY` — it can't verify your session and returns 401. Check
`curl <api-url>/api/auth/me` reports `"clerk_configured": true`.

---

## Running it locally instead

```bash
pip install -e ".[dev,server,live]"
uvicorn server.app:app --port 8077          # API
cd dashboard && npm install && npm run dev  # dashboard on :3000
```

The dashboard defaults to `http://127.0.0.1:8077` when `NEXT_PUBLIC_API_URL`
is unset, so local needs no configuration.
