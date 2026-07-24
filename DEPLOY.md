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
4. Sanity check: `curl <that-url>/api/health` → `{"ok":true,"version":"0.3.0"}`

The blueprint sets `SOUNDCHECK_SECRET` (`generateValue: true`) — it signs
session tokens and must stay stable across restarts, or everyone gets logged
out on each deploy. If you ever run the API another way, set that env var
yourself to a long random string.

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
3. Add an environment variable:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | the Render URL from step 1, no trailing slash |

4. Deploy.

> `NEXT_PUBLIC_*` variables are inlined **at build time**, not read at runtime.
> If you change the API URL later you must redeploy, not just edit the variable.

## 3. Verify

Open the Vercel URL and click **Run test — no signup**. It should navigate to a
run page, poll while the call runs, and land on a verdict. Then tick *"Simulate
a degraded config"* and run again — the gate should fail on `ttfa_ms`.

That path needs no API key: it drives the built-in deterministic mock agent.
Testing a **real** ElevenLabs agent is opt-in per run, and the credentials are
used for that request only — never written to the database or the logs.

---

## Running it locally instead

```bash
pip install -e ".[dev,server,live]"
uvicorn server.app:app --port 8077          # API
cd dashboard && npm install && npm run dev  # dashboard on :3000
```

The dashboard defaults to `http://127.0.0.1:8077` when `NEXT_PUBLIC_API_URL`
is unset, so local needs no configuration.
