# SDW · De kantine

Application version **0.1.6** is defined in `app/__init__.py` and used by FastAPI.
Follow `AGENTS.md`: increase the patch version for each change and start every
commit message with that version before committing and pushing.

**Live demonstration:** https://datariotfc.alwaysdata.net/ — FastAPI is connected to
PostgreSQL, both test logins pass, and the scheduled worker runs every ten minutes.
See [SESSION_HANDOFF.md](SESSION_HANDOFF.md) for the latest verification and remaining
email / official match-feed requirements.

A Dutch/English parent portal and coordinator dashboard for ASC SDW, Amsterdam West.
Python 3 / FastAPI, SQLAlchemy, Alembic and PostgreSQL, deployed as an alwaysdata
**User program** with Uvicorn. The frontend is responsive HTML, CSS and JavaScript,
served from the same origin without a separate Node build or external assets.

## Current configuration

The initial installation is an explicit **demonstration environment**. Seeded parents
and fixtures are fictional, visibly marked, and email is simulated. There are separate
test accounts `beheer.test` (coordinator) and `ouder.test` (parent). Random passwords
are in the ignored local `test-credentials.txt`. Only Argon2id password hashes are
stored in the application database. Never commit this file, `.env` or `.provision.env`.

Real email and automatic live fixture retrieval still require sender setup and the
club's credentials. The 7–8 November 2026 home programme is a manually verified
official club snapshot; source links and verification time are displayed. Staffing
is explicitly fictional and email remains simulated. PostgreSQL, the public website
process and the scheduler are provisioned.

## SDW branding and link previews

The demo uses the current red-and-white SDW crest and the name **SDW Kantine**.
Original image provenance is recorded in [branding/SOURCES.md](app/static/branding/SOURCES.md).
The login page and sidebar, browser favicon, Android/iPhone icons, manifest, HTML
title and server-rendered Open Graph / Twitter metadata use this branding. Preview
images are hosted publicly on the app origin, independent of a parent login or JavaScript.
Versioned image/icon URLs help refresh cached assets; already-sent previews may persist.
The hosting address remains `datariotfc.alwaysdata.net`.

## Mobile access

Open the same HTTPS address on a phone. Both parent and coordinator views adapt to
small screens, with bottom navigation, touch controls, readable table cards and a
keyboard-accessible menu. Dutch and English use the same accounts and database.

For a home-screen app, open the site in **Safari on iPhone**, tap Share and choose
**Add to Home Screen**. In **Chrome on Android**, open the menu and choose **Install
app / Add to Home screen**. A supported browser can also show an Install app button
under My account. This uses a web-app manifest, standalone display and app icons;
it does not require an app-store download. See the [MDN installation guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable).

An internet connection is required for current schedules and all responses. The
app shows a connection notice while offline and never queues responses for later.
Private responses use `Cache-Control: no-store`; no offline data cache is installed.
Session cookies remain device-specific and expire after eight hours. Rebuild icons
with `scripts/build_icons.ps1`; regenerate English assets with `scripts/build_locales.py`.

## Local development

For a complete isolated PostgreSQL + scheduler + SMTP/IMAP + Roundcube webmail environment, see
[the Docker development guide](dev/README.md). On PowerShell or a Unix shell:

```text
python scripts/dev.py up
python scripts/dev.py credentials
python scripts/dev.py test
```

The app opens at http://127.0.0.1:8000, Roundcube webmail at http://127.0.0.1:8080,
and the Mailpit message inspector at http://127.0.0.1:8025. Named test inboxes include
`anna@example.invalid` through the six accounts listed in the guide; their app
logins are `anna.test`, `bram.test`, `cem.test`, `dana.test`, `els.test`, `finn.test`.
The credentials command shows app and webmail passwords separately. Mail services
have no internet route and browser ports bind only to loopback. Docker generates
its own ignored configuration and fictional
data; it does not use the root `.env`, existing SQLite data or alwaysdata secrets.
Adminer at http://127.0.0.1:8081 provides browser access to the local PostgreSQL
database. Choose PostgreSQL, server `db`, user `sdw`, database `sdw_local`; the
password is `LOCAL_DB_PASSWORD` in ignored `.local/docker.env`.
The test command uses a disposable separate PostgreSQL stack. The non-Docker
SQLite workflow below remains available.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python scripts\local_setup.py
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Local setup uses SQLite to make the demo easy to run;
**production requires PostgreSQL**. For development against PostgreSQL, use a
dedicated database in `DATABASE_URL`, then run `python -m alembic upgrade head`.
`SECRET_KEY` is required and must contain at least 32 random characters.

Run tests with `python -m pytest -q`. The fast test suite uses isolated databases and
fake SMTP/fixture transports; it never sends emails or changes hosted data.

Parents can switch between Nederlands and English on both the login page and the
dashboard. Their choice is saved for subsequent invitation/cancellation emails.
Coordinators can choose a preferred language when creating or editing a parent.
The shared Dutch UI source and reviewed `app/locales/en.json` catalogue generate the
English bundle via `python scripts/build_locales.py`; staging runs this automatically.
Dates always use Amsterdam time, independently of the selected display language.
The default and initial existing open shifts have **three parent places each**.

## Visitor statistics and sharing links

The coordinator's **Visitors / Bezoekers** page (on a phone: **More / Meer**) shows
unique browsers, page views, mobile/tablet visitors, repeat views, a daily chart and
counts per labelled share link. Filters cover 7/30/90 days and mobile-only traffic;
figures refresh every 30 seconds while the page is visible. Create a new link for
each group or sharing round and use its `?share=...` URL. Ordinary links still count
under Direct / other links. Counting started with deployment; there is no historical
visitor data from before this feature.

A first-party HttpOnly/Secure/SameSite cookie contains a signed random visitor ID,
expiring after 90 days without extending its lifetime on each visit. Only an HMAC
pseudonym is stored in PostgreSQL, with Amsterdam calendar day, first/last visit time,
share-link ID, mobile/desktop category and counts. No IP addresses, full user agents,
referrers, invitation tokens, full URLs, precise location or links to parent accounts
are stored in these analytics tables. Cookie IDs are pseudonymous, not proof of a
person's identity. Several people sharing an IP remain separate browsers; using
another browser/device, clearing cookies or disabling them can count a person again.
Repeated page loads increase views, not unique browsers. Cross-link/date totals use
COUNT DISTINCT rather than adding daily or per-link unique counts.

Public login and app pages disclose the limited analytics and link to privacy controls.
Opting out deletes the visitor cookie; account/scheduling access continues normally.
DNT/GPC requests and known bots/previews are excluded, as are signed-in coordinators.
An anonymous coordinator before login can still produce a visit. No third-party
analytics script or advertising tracker is used. The ordinary ten-minute worker
prunes visitor records outside the 90-day window. Hosting access logs are separate
from this app's analytics and remain subject to the hosting provider's settings.
For context on limited first-party analytics cookies, see the [Dutch government
explanation](https://www.rijksoverheid.nl/themas/overheid-en-democratie/privacy-en-persoonsgegevens/vraag-en-antwoord/telecommunicatie/mag-een-website-ongevraagd-cookies-plaatsen).

`GET /api/admin/analytics` is coordinator-only; creation of share links also requires
CSRF. Public collection accepts only a validated share code and a same-origin JSON
request with a custom header. Analytics never grants access to the scheduler.

## Database design

There are 20 application tables (plus Alembic's version table). The original 17 are:

- `clubs`, `venues`, `teams`: club identity, approved home locations and teams.
- `users`, `parent_teams`: individual accounts and optional team associations.
- `fixtures`, `shifts`, `shift_fixtures`: source fixtures, staffing windows and their links.
- `planning_policies`, `unavailability`: configurable rules and private availability blocks.
- `invitations`, `email_outbox`: immutable offer history, response deadlines and delivery retries.
- `login_sessions`, `login_attempts`: revocable sessions and persistent login throttling.
- `audit_events`, `sync_runs`, `job_runs`: operational and coordinator history.

The analytics revision adds `share_links` and `visitor_days` for limited, first-party
sharing statistics, separate from parent account data. The fictional staffing revision
adds `demo_assignments`, separate from invitations and real parent responses.

Foreign keys, unique constraints and checks protect identity, valid states, shift
duration, headcount and maximum 48-hour response periods. Schema changes belong in
new Alembic revisions; application startup never silently recreates production tables.

## Scheduling and fairness

1. Only a scheduled SDW **home fixture at Sportpark Spieringhorn in Amsterdam** can
   produce a shift. Away games, cancellations and unapproved locations do not.
2. Home games are grouped by Amsterdam date/venue. The canteen opens at 08:00
   (`CANTEEN_OPENING_HOUR=8`) and uses consecutive full shifts through two hours
   after the final kickoff, rounding the last shift up. The current policy is
   two hours and three places. The coordinator can adjust times/headcount.
   With the verified weekend programme, Saturday 7 November closes at 18:00
   and Sunday 8 November at 16:00 (Amsterdam).
   With `DEMO_STAFFING_ENABLED=true` in demo mode, separate `demo_assignments`
   hold fictional names, including six extra placeholders without accounts/email.
   They reserve places and observe fairness but are never parent confirmations,
   attendance or messages. These records remain attached to cancelled historical shifts.
3. Candidates must be active volunteers in the same demo/live environment, not
   unavailable, not already offered the shift, and not offered another duty within
   the configured gap (default 14 days). All non-cancelled offers count, including
   declines/timeouts, to prevent repeatedly bothering the same parent.
4. Never offer adjacent home matchdays to the same parent, even when those dates
   are further apart than the minimum day gap. Rank eligible candidates by fewest
   confirmed/completed duties, fewest offers in 90 days, longest time since the last
   offer, then stable account ID. Team links are informational; the pool is club-wide.
5. Reserve a slot when an invitation is queued. Start the response deadline only
   after SMTP acceptance (or simulated delivery in demo mode). Deadline is the earlier
   of 48 hours and two hours before shift start. No new offer is made within six hours
   of shift start. Urgent gaps remain visible for the coordinator.
6. Declines trigger immediate replacement selection; the scheduled job expires
   unanswered offers and queues replacements. Parents cannot confirm after the
   exact deadline, even before the next job runs. The job runs every ten minutes,
   so replacement emails can follow expiry by up to roughly ten minutes.
7. Strict fairness is never silently relaxed. If the pool is exhausted, show an open
   place and let the coordinator resolve it. Increase the parent pool or adjust the
   documented policy rather than repeatedly proposing the same parent.

PostgreSQL transaction advisory locks serialize cron, manual planning, confirmations
and shift edits. This prevents parallel workers from overfilling slots. A local lock
is provided only for the development database. Historical decisions are audited.

Fixture moves/cancellations invalidate affected future offers, send cancellation
notices for delivered/confirmed duties, and regenerate managed shifts. Manually
adjusted duties move to review rather than being silently overwritten. A manually
cancelled matchday is not recreated by the next cron tick. Changing shift times
cancels the old shift and retains its history; replacement offers require fresh
confirmation. Attendance is explicitly recorded by the coordinator after a duty;
confirmation is never assumed to mean a parent actually attended.

## Authentication and data handling

- Argon2id with a random 128-bit salt, 64 MiB memory, three iterations and four lanes.
- No public registration. Only a coordinator creates parent accounts. Minimum new
  password length is 12 characters; passwords are never returned in APIs or logs.
- Random opaque eight-hour session cookies, `HttpOnly`, `Secure` in production,
  `SameSite=Lax`. Only session token hashes are stored. Login rotates the session;
  changing a password revokes all sessions.
- CSRF tokens and same-origin checks on authenticated changes; login is throttled
  per username and client address. No API documentation is publicly exposed.
- Parents see their own invitations and availability. Other parents' contact
  details, delivery data and administration APIs require the coordinator role.
- Invitation tokens are 256-bit random values stored only as SHA-256 hashes. The
  email URL opens a page; **the invited parent must log in with their username and
  password and explicitly submit their answer**. GET requests never accept duties.
- Queued email bodies are encrypted with a key derived from `SECRET_KEY`; delivered
  bodies are erased. Keep the secret stable while queued mail exists.
- No child names or player personal information are collected. Team associations
  are optional. UTC is stored; display and matchday rules use Europe/Amsterdam.
- CSP, frame blocking, no-referrer policy and no-store responses protect the portal.
  Uvicorn request access logging is disabled so invitation tokens are not written to
  application access logs. Hosting's own logs still need normal retention controls.

Use distinct coordinator accounts before real parent data is entered; deactivate the
shared test accounts. Normal parents cannot obtain coordinator access through the API.

## Email: Proton requirements and alternatives

[Proton SMTP submission](https://proton.me/support/smtp-submission) currently supports
**paid Proton Mail plans with a custom-domain address**. Generate a dedicated SMTP
token under Settings → IMAP/SMTP → SMTP tokens. The normal Proton login password is
not the SMTP password. A free `@proton.me` account does not provide this submission
feature. Proton Bridge is not required for SMTP submission.

The supplied `Datariotfc@proton.me` account is on the free plan without a custom
domain. It therefore cannot currently be used as the SMTP sender. Email remains
simulated until an alternative eligible sender is configured; no free Proton login
password is requested or attempted against SMTP.

Set these **on the server**, in `/home/datariotfc/sdw-kantine/.env` with mode `0600`:

```dotenv
SMTP_HOST=smtp.protonmail.ch
SMTP_PORT=587
SMTP_USERNAME=kantine@your-club-domain.nl
SMTP_PASSWORD=YOUR_SMTP_TOKEN
SMTP_FROM=kantine@your-club-domain.nl
```

Port 587 uses STARTTLS with certificate verification; port 465 uses implicit TLS.
Set up the domain's SPF/DKIM/DMARC according to Proton's instructions. Test delivery
to a club-controlled inbox before enabling live invitations.

If Proton's plan does not qualify, the app's standard SMTP adapter can instead use
[alwaysdata mail](https://help.alwaysdata.com/en/docs/emails/use-an-email-address/)
or a transactional SMTP provider. No code redesign is needed. No automatic fallback
impersonates a Proton sender.

Delivery failures retain queued invitations and retry with bounded exponential
backoff; failed delivery does not consume a parent's reply window. Database and SMTP
cannot share an atomic transaction: delivery is **at least once**, with a stable
Message-ID to assist deduplication. A rare crash immediately after SMTP acceptance
can cause a duplicate email, but its invitation is still single-use and never
creates a second slot or second confirmation.

## Automatic match data: what was found

- SDW publishes its [club-wide programme](https://www.ascsdw.nl/116/programma/) and
  per-team programme pages through VoetbalAssist. Its public website blocked direct
  automated retrieval during investigation; cached search results are not an adequate
  live source for staffing duties. No anti-bot bypass is implemented.
- [Sportlink Club.Dataservice](https://sportlinkservices.freshdesk.com/nl/support/solutions/articles/9000062942)
  provides a documented `programma` feed: stable match IDs, team IDs/names, kickoff,
  club relation codes, accommodation, city and status. The club must have a paid
  Club.Dataservice subscription and provide its Client ID. These public programme
  fields need no personal Sportlink login, but the **Client ID is required**.
- [VoetbalAssist's existing KNVB data integration](https://www.voetbalassist.nl/FAQ-Dataservice/)
  is another route for SDW to request an authorized feed/export from its current
  website provider. Its existing subscription does not prove it includes a separate
  Sportlink Club.Dataservice Client ID.
- [Voetbal Data Centre](https://voetbaldatacentre.nl/) is an official commercial
  alternative for Dutch amateur match data. It would need a separate agreement;
  no purchase or subscription has been made.

The Sportlink adapter is implemented in `app/fixtures.py`; configure:

```dotenv
SPORTLINK_CLIENT_ID=provided-by-the-club
SPORTLINK_CLUB_CODE=the-club-relation-code
```

The worker refreshes it hourly, up to the API's 42-day horizon and 500-match limit.
A saturated response is rejected as incomplete. A failed/invalid response preserves
existing fixtures. Missing future games become review items; cancellation is never
inferred from a network failure. No new automatic invitations use feed fixtures
unverified for more than 24 hours. Explicit cancellation/time changes reconcile
affected shifts. Only Amsterdam/Spieringhorn locations are approved automatically;
incomplete venue information remains for review, not guessed.

A one-time public club snapshot can be imported with `python -m app.club_snapshot`
using a reviewed JSON manifest on stdin. It validates timestamps, full team names,
source URLs, pitch/venue evidence and the cancellation check before changing data.
It retains historical demo fixtures for review, cancels their future shifts with
audit history, and keeps fictional staffing separate from real match facts. Snapshot
coverage, capture time and match links appear in both languages. This is a manual
snapshot, not a working automatic feed; fixtures can change after verification.
The 7–8 November home snapshot includes 31 games, including an internal friendly.
The original browser HTML, detail observations and reviewed manifest are retained
locally under `research/`; only the manifest is imported over authorized SSH.

Until authorized live data is configured, the coordinator can enter verified games
manually, including away games for programme visibility. **Demo fixtures are not a
claim about SDW's actual programme.** End-to-end feed access remains to be tested
with the club's real Client ID and club code.

## alwaysdata deployment

The platform documents all required hosting building blocks:
[Python ASGI with Uvicorn](https://help.alwaysdata.com/en/docs/web-hosting/languages/python/configuration/#asgi-deployment),
[PostgreSQL](https://help.alwaysdata.com/en/docs/web-hosting/databases/postgresql/), and
[scheduled tasks](https://help.alwaysdata.com/en/docs/web-hosting/tasks/).
Python 3.13 and `psql` were verified over SSH on this account. SMTP additionally
depends on Proton's account requirements above. Runtime capacity remains subject
to the selected alwaysdata plan's limits; no billing changes are performed.

1. Keep the SSH private key at `C:\Users\audio\.ssh\id_ed25519_datariotfc_alwaysdata`.
2. Run `python scripts/stage.py` to archive only source, upload it, create a server
   virtualenv and install dependencies. The alwaysdata pip configuration needs
   `--no-user` inside the virtualenv; the script includes it.
3. Create an alwaysdata API token with access **only to the datariotfc account** and
   the database/site/scheduled-task resources. Save it locally in `.provision.env`:

   ```dotenv
   ALWAYSDATA_API_TOKEN=your-token
   ```

4. Run `python scripts/provision.py`. It creates a dedicated `datariotfc_kantine`
   PostgreSQL database/user, transfers generated server secrets through SSH stdin,
   migrates the schema, seeds the demo, registers a ten-minute job and configures the
   default `datariotfc.alwaysdata.net` website as a User program with HTTPS enforced.
   It never changes unrelated websites or account billing. Before replacing an
   existing site, its API configuration is retained in ignored `deployment-state.json`.
5. Verify `https://datariotfc.alwaysdata.net/health`, both test logins and role access,
   and the worker heartbeat. Verify the database connection and live cron execution
   before calling deployment complete. Remove/revoke the provisioning token when done.

The provisioner is resumable and retains existing server `.env` settings and API
resources. If a database user with the same name existed independently, provide its
actual password securely rather than overwriting it. API failures print only resource
path, status and field names, never a response that could echo credentials.

Manual equivalent:

- Database/user: PostgreSQL, TLS required, user permissions only on the app database.
- Website type: **User program**; working directory: `sdw-kantine`.
- Command: `/home/datariotfc/sdw-kantine/.venv/bin/python /home/datariotfc/sdw-kantine/scripts/start.py`.
- The launcher uses alwaysdata's `IP` and `PORT` variables and a single worker.
- Job: `/home/datariotfc/sdw-kantine/.venv/bin/python /home/datariotfc/sdw-kantine/scripts/job.py`.
- Job directory: `sdw-kantine`; schedule: `*/10 * * * *`.
- Jobs and web processes read the same server `.env` without exporting secrets in
  the public website directory or scheduler command.

## Moving from demonstration to real use

Keep the demonstration database available for review. Provision a separate empty
production database, set `DEMO_MODE=false`, a new secret and the live SMTP/fixture
settings, then migrate and initialize it with `python -m app.seed` (credentials on
stdin). In live mode seed creates only the club, venue, policy and initial coordinator;
it does not insert fictional matches or parents and leaves automation disabled.
Create real named coordinator/parent accounts, verify fixture identity/location and
email delivery, then enable automatic invitations. Don't mix real parent contact
details into a shared demonstration environment.

For database backups use alwaysdata's managed backups and retain a tested restore
procedure. Back up the server `.env` separately in an appropriate secret store.
The UI shows delivery problems, feed status and the latest worker heartbeat; review
unfilled shifts and stale sources regularly. Password reset delivery, SMS, child/member
administration, inventory and accounting are outside this initial canteen scheduler.
