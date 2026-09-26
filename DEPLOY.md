# Deploying FoodFlow: Vercel + Supabase

Two Vercel projects from this repo (backend, frontend) and one Supabase Postgres database.
The backend's scheduled jobs run through `/internal/jobs/run`, called every minute by Supabase `pg_cron`.

| Piece | Where | Root directory |
|---|---|---|
| API (FastAPI) | Vercel project `foodflow-api` | `backend` |
| Web app (Next.js) | Vercel project `foodflow-web` | `frontend` |
| Database | Supabase Postgres | |
| Scheduled jobs | Supabase `pg_cron` + `pg_net` (or Vercel Cron on Pro) | |

## 1. Supabase

1. Create a project in the region nearest your Vercel functions (Vercel's default is Washington, D.C., `iad1`:
   pick `us-east-1`).
2. **Project Settings → Database → Connection string**. Copy:
   - **Transaction pooler** (port `6543`): the app's `DATABASE_URL`.
   - **Session pooler** (port `5432` on the pooler host): for migrations from your machine. The "direct"
     `db.<ref>.supabase.co` host is IPv6-only unless you buy the IPv4 add-on.
   Plain `postgresql://` URLs are fine; the app switches them to its psycopg driver.
3. Create the tables (from `backend/`, with your venv active):
   ```bash
   DATABASE_URL="postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres" alembic upgrade head
   ```
4. Create the first admin (the password is asked for twice, never put on the command line):
   ```bash
   DATABASE_URL="<same session pooler URL>" python -m scripts.create_admin you@yourorg.org "Your Name"
   ```
5. Supabase Auth, Storage and the Data API are not used. The app connects as the database owner, and the
   dashboard will warn that row-level security is off on these tables. That is expected: never publish the
   project's `anon` key, and consider turning the Data API off (**Project Settings → Data API**).

## 2. Backend on Vercel

1. **Add New → Project**, import the repo, **Root Directory** `backend`. Vercel detects FastAPI
   (`app/main.py`) and Python 3.12 (`.python-version`).
2. `backend/vercel.json` already sets the build command (`python -m scripts.build_models`, which trains the ETA
   and surplus models into the bundle; the function disk is read-only) and excludes tests and migrations.
3. Environment variables (Production):

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the **transaction pooler** URL (port 6543) |
   | `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` (the app refuses to start without 32+ characters) |
   | `DEMO_MODE` | `false` |
   | `CRON_SECRET` | another random string (16+ characters) |
   | `CORS_ORIGINS` | `https://<your-web-app>.vercel.app` (comma-separate your custom domain later) |
   | `CORS_ORIGIN_REGEX` | optional, for preview deploys: `https://foodflow-web-[a-z0-9-]+-<team>\.vercel\.app` |
   | `TIMEZONE` | `America/New_York` |
   | `ROUTING_PROVIDER` / `MAPBOX_ACCESS_TOKEN` | `mapbox` + a token, or `offline`. The default uses the free public OSRM server, with no uptime guarantee. |
   | `SMTP_*`, `TWILIO_*` | optional, for email/SMS notifications (otherwise they are only logged) |

   `SERVERLESS` and `RUN_SCHEDULER` need no setting: on Vercel the app turns off its connection pool and its
   in-process job loop automatically.
4. Deploy. Check `https://<api>.vercel.app/` answers `{"status":"ok","demo_mode":false}` and the build log shows
   `ETA model ready` and `surplus model ready`.

## 3. Frontend on Vercel

1. **Add New → Project**, same repo, **Root Directory** `frontend`.
2. Environment variables: `NEXT_PUBLIC_API_URL=https://<api>.vercel.app` (read at build time: redeploy after
   changing it), optional `NEXT_PUBLIC_MAPBOX_TOKEN`, `NEXT_PUBLIC_SITE_URL`.
3. Deploy. Put the resulting URL in the backend's `CORS_ORIGINS` and redeploy the backend.

## 4. Scheduled jobs (every minute)

The jobs catch volunteer no-shows, expire unsafe food, move simulated vehicles and re-route drop-offs.
Overlapping or duplicate calls are safe (they run under a lease in the database).

**Supabase (any Vercel plan)**: in the SQL editor:
```sql
create extension if not exists pg_cron;
create extension if not exists pg_net;
select cron.schedule('foodflow-jobs', '* * * * *', $$
  select net.http_get(
    url := 'https://<api>.vercel.app/internal/jobs/run',
    headers := jsonb_build_object('Authorization', 'Bearer <CRON_SECRET>'),
    timeout_milliseconds := 60000)
$$);
```
Check it with `select * from cron.job_run_details order by start_time desc limit 5;` and the `net._http_response`
table. The secret sits in the job definition, visible to database admins only.

**Vercel Cron (Pro plan only)**: add `"crons": [{"path": "/internal/jobs/run", "schedule": "* * * * *"}]` to
`backend/vercel.json`. Vercel sends `CRON_SECRET` itself. On the Hobby plan an every-minute cron fails the deploy.

## 5. Go-live checks

1. Sign up as a restaurant, an organization and a volunteer on the live site.
2. As the admin, verify the organization's EIN; complete its three onboarding questions.
3. Post a rescue and take it through accept, pickup, deliver and receipt.
4. Post a rescue with a deadline a few minutes out and watch it expire within a minute or two (jobs running).
5. Enter a wrong password 10 times: the 11th attempt answers "Too many failed sign-in attempts".
6. Add your custom domain to both projects, then update `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL`.

## Changing the schema later

Edit `backend/app/models.py`, then from `backend/`:
```bash
alembic revision --autogenerate -m "what changed"   # review the generated file in migrations/versions/
DATABASE_URL="<session pooler URL>" alembic upgrade head
```
`tests/test_deployment.py` fails if the models and the migrations ever disagree.

## Still open

- Email is never verified and there is no password reset (no email service). A manager or admin cannot reset
  someone's password yet either.
- Error tracking (e.g. Sentry) and a privacy page: you store phone numbers and volunteer home locations.
- Backups: daily on Supabase by default; point-in-time recovery needs a paid plan.
