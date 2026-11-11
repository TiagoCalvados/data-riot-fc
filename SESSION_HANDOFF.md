# SDW Kantine — current handoff

Updated: 2026-11-05T17:08:52+01:00.

## Live and verified

- Public HTTPS app: https://datariotfc.alwaysdata.net/ (English: /?lang=en).
- FastAPI User program, site ID **1100302**. Root: `/home/datariotfc/sdw-kantine`.
- PostgreSQL database and dedicated app-only user: `datariotfc_kantine`.
  Eighteen database tables including Alembic. Strong Argon2id salted password hashes,
  revocable sessions, CSRF checks, role restrictions, encrypted outbox, audit history.
- Scheduled task **37519**, `*/10 * * * *`, command
  `/home/datariotfc/sdw-kantine/.venv/bin/python /home/datariotfc/sdw-kantine/scripts/job.py`,
  working directory `sdw-kantine`, environment `PYTHON_VERSION=3.13`.
- Automatic execution verified in PostgreSQL: many successful ten-minute heartbeats.
  The final HTTPS smoke check also required a successful heartbeat within 30 minutes.
- Both test logins passed live, including parent-only visibility, coordinator denial,
  no password hashes in dashboard output, and logout invalidation.
- Three parent places per demo shift; twelve demo shifts visible to the coordinator.
- Email remains simulated and all seeded people/fixtures are visibly fictional.
- Existing desktop shortcut `C:/Users/audio/OneDrive/Bureaublad/SDW Kantine.url`
  now opens the public HTTPS app.

## Mobile release — published 5 November 2026

- Same URL, database and accounts on phones and computers; Dutch and English.
- Bottom navigation for both roles, larger touch controls, labelled cards for tables,
  responsive shift rows, safe-area spacing, accessible drawer with close/backdrop,
  Escape and keyboard focus containment, full-width phone forms/dialogs.
- Web-app manifest, standalone display and 180/192/512px app icons branded SDW Kantine (updated 5 November).
  Safari iPhone: Share > Add to Home Screen. Chrome Android: menu > Install app /
  Add to Home screen. Instructions also appear under My account.
- Internet required for current schedules and responses; connection notice on loss
  of connectivity. No service worker or offline private-data cache is installed.
  No offline acceptance/decline queue. Eight-hour sessions are per browser/device.
- Language selector updates the query parameter while retaining invitation links.
  Sign-out clears rendered dashboard data and resets navigation before next login.
- Coordinator dashboard, drawer and parent cards visually inspected in Chrome at
  390x844 CSS pixels. Chrome displayed the app-install entry point locally.
- Native browser control stopped when it could not establish the current URL with
  sufficient confidence while switching to hosting administration. No further UI
  input was sent. Publication and final verification completed through authorized
  SSH and HTTPS tools. Physical iPhone/Android installation has not been tested.
- Final HTTPS checks compare public assets with reviewed source hashes and verify
  both mobile HTML languages, manifest, icons, test accounts and recent job heartbeat.
- **36 pytest tests passed**; Dutch and English JavaScript syntax checks passed.
  A test-client dependency deprecation warning remains, without test failures.

## Authorization and private files

The earlier credential approval blocker was resolved: the user explicitly authorized
saving the generated app database password in alwaysdata and private server config.
Deployment then completed. Two-factor authentication was not the cause.

- Local private credentials: ignored `test-credentials.txt` JSON; preserve values.
  Test usernames: `beheer.test` (coordinator), `ouder.test` (parent).
  Do not print database password, secret key, SSH private key or API tokens.
- SSH key: `C:/Users/audio/.ssh/id_ed25519_datariotfc_alwaysdata`.
  Target: `datariotfc@ssh-datariotfc.alwaysdata.net`; host-key checking required.
- Production `.env` is private mode0600, PostgreSQL TLS required, secure cookies,
  `BASE_URL=https://datariotfc.alwaysdata.net`, `DEMO_MODE=true`.
- Local `.env` uses SQLite `development.db`; do not upload local data or secrets.
- `.provision.env` exists but its alwaysdata API token is blank. No token is needed
  for routine source uploads. Website configuration changes/restart require hosting
  administration or an account-scoped API token. HTTP processes are separate from
  SSH (`ssh2`); do not assume they can be killed from the SSH machine.
- Website command:
  `/home/datariotfc/sdw-kantine/.venv/bin/python /home/datariotfc/sdw-kantine/scripts/start.py`.
  Working directory `sdw-kantine`, `PYTHON_VERSION=3.13`, force HTTPS.
- Do not reset the unrelated default PostgreSQL user's password.

## Remaining requirements before real club operations

1. Email: free `Datariotfc@proton.me` has no Proton SMTP submission access. Choose
   an eligible Proton plan/custom domain/SMTP token or an alternative SMTP sender.
   No real invitation emails have been sent. Keep simulation until sender setup and
   real recipient accounts are ready. Do not purchase a plan without instruction.
2. Match feed: adapter for official Sportlink Club.Dataservice is implemented;
   obtain SDW's authorized Client ID and club relation code, or an approved feed
   from its website provider. Public SDW retrieval was blocked; no bypass attempted.
   Manual fixture entry is available. Seeded matches are fictional.
3. Replace demo parents and fixtures with verified club data and explicitly review
   the policy before switching out of demo mode. Do not erase demo/audit data blindly.

## Requirements retained

ASC SDW at Sportpark Spieringhorn, Amsterdam West. Python3 FastAPI/PostgreSQL.
Dutch/English UI and invitation language. Three parents per adjustable two-hour
shift. Approved home fixtures only. No consecutive home matchday proposals;
configurable gap (default14 days), fairness includes offered work. Maximum48h reply
period begins after successful delivery; declines/expiry select a replacement.
A ten-minute worker handles expiry, delivery/retries and hourly feed sync. Stale
feeds stop new automatic offers. Parents see only their own invitations.

## Resume and verification

- Local preview: `.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log`.
- Build locales: `.venv/Scripts/python scripts/build_locales.py`.
- Build app icons: `scripts/build_icons.ps1` (System.Drawing; no runtime dependency).
- Tests: `.venv/Scripts/python -m pytest -q -p no:cacheprovider`.
- Publish reviewed source: `.venv/Scripts/python scripts/stage.py` (uses existing SSH
  key; does not transfer local credentials/database or reinitialize PostgreSQL).
- Live checks: `.venv/Scripts/python scripts/smoke.py https://datariotfc.alwaysdata.net --require-scheduler`.
- This Windows environment injects `SSLKEYLOGFILE` pointing to a protected AVG pipe;
  clear that environment variable only for verification subprocesses if Python TLS
  context creation fails. Certificate checking remains enabled. Restricted-sandbox
  networking/process execution may require the standard approved escalation.
- Local snapshots: `scripts/save_snapshot.py`. Archives exclude `.env`, credentials,
  API tokens and SSH keys. They include a consistent local SQLite demo snapshot,
  **not** the hosted PostgreSQL database. Keep originals of private config in place.
- No Git repository was initialized. Source, README and this handoff are saved directly.

See README.md for architecture, security boundaries, official integration sources
and operations. Current deployment metadata is in ignored deployment-state.json.

## Latest branding update — 5 November 2026

The user requested the real SDW logo and SDW naming in shared links. Product-visible
Data Riot FC naming was replaced with SDW Kantine in both languages, the title,
Apple metadata, app manifest, footer and account installation help. The current
red-and-white club crest is used, not the historical circular logo. Original club
profile JPEG and official linked-webshop favicon are stored unchanged; provenance
is in app/static/branding/SOURCES.md. Icon sizes are proportional derivatives with
a separate maskable icon. Login/sidebar show the real crest. Static Open Graph and
Twitter metadata expose SDW title, description and a public absolute HTTPS logo URL
to logged-out preview crawlers. Versioned icon/image URLs use sdw-20261105.
The hostname is still datariotfc.alwaysdata.net; no hosting-account rename occurred.
Brand metadata and icons are covered by regression checks (37 tests now pass).
Share a fresh URL with ?v=sdw-20261105 if a messaging app retains an old preview.
Existing installed Android shortcuts may need to be added again to refresh name/icon.

## Visitor tracker — deployed and verified 2026-11-05T20:09:17+01:00

User requested unique visitors and mobile visit counts when sharing the demo.
Implemented first-party limited analytics in app/analytics.py, models ShareLink and
VisitorDay, and Alembic revision c42d98ac7140. There are now 19 app tables plus the
Alembic version table. Production schema upgraded without reseeding or changing
parent/password data. Before migration, a private PostgreSQL custom-format backup
was saved at /home/datariotfc/private-backups/sdw-before-analytics-20261105T190232Z.dump
(mode0600, directory0700). This is a server-side database backup; local source
snapshots still contain only the local SQLite demo database.

The existing hosting site #1100302 was restarted successfully through its signed-in
administration UI. PostgreSQL, app logins and the ten-minute scheduled worker all
passed public HTTP smoke checks afterward. New analytics APIs and SQL upserts were
verified against real PostgreSQL: one mobile browser loading three times counted
1 unique / 3 page views; a second browser on the same originating IP added a new
unique visitor. The mobile-only filter and coordinator exclusion passed. Only those
two synthetic verification browser rows were deleted afterward, preserving other
visitors. Anonymous pre-login coordinator/visual-check visits may count normally.

Public pages collect only page loads (not every internal navigation) using a signed
random first-party HttpOnly/Secure/SameSite cookie with fixed90-day lifetime. The
DB stores an HMAC pseudonym, Amsterdam calendar day, first/last visit times, share
link, coarse mobile/desktop category and view count. No raw IP, full user agent,
referrer, full visited URL, invitation token, location or parent-account link is
stored in these analytics tables. The ordinary worker prunes records outside the
90-day reporting window. Privacy controls on login and app footer let visitors opt
out and delete the visitor cookie. DNT/GPC requests and known bots/previews are not
counted. Signed-in coordinators are excluded. Counts estimate browsers, not people;
multiple devices/cleared cookies/blocked cookies affect uniqueness. Do not claim
these cookie-based IDs are fully anonymous or that hosting logs contain no IPs.

Coordinator UI: More > Visitors (Meer > Bezoekers) on phones, Visitors in desktop
navigation. Period7/30/90 days; mobile/tablet-only filter; totals, per-link table and
last14-day chart; active visible page polls every30 seconds. Create share link makes
a labelled URL, with Copy link and manual-copy fallback. Reports expose aggregate
counts only. Parent403 and unauthenticated401 boundaries verified in smoke tests.
Create-link writes require session+CSRF. Public collection requires a custom header;
existing same-origin security middleware blocks cross-site browser writes.

First real share link (label SDW demo):
https://datariotfc.alwaysdata.net/?share=nsk2lVQNtzyUkqCH
Use a new share link for every sharing round that needs separate attribution.
Ordinary URLs count under Direct / other links. There is no pre-deployment history.

44 pytest tests passed; JavaScript for both languages passed syntax checks; Alembic
reported no missing operations. Desktop and390x844 phone views visually verified.
Screenshots: research/visitors-dashboard-en.png and research/visitors-mobile-en.png.
Browser task completed normally; coordinator dashboard remained open on desktop.
Latest source and operational notes are included in the local backups/ snapshot.

## Fixture correction investigation — 6 November 2026

No hosted changes or imports: production still has 16 fictional fixtures / 12 demo shifts; live Sportlink Client ID and club code are absent. Public programme is a dynamic template; direct retrieval was explicitly blocked. Older official search snapshots do not verify current complete coverage or cancellations. See research/fixture-investigation-20261106.md for evidence, required input, successful hosted/mobile-desktop checks and the retained 08:00 opening / two-hour blocks / three fictional parents requirement. A current club-approved programme export or accessible approved feed is needed before deriving the closing block and replacing demo planning. Email simulation and all parent/history records remain unchanged.

Three focused fixture/feed tests passed. Initial broader restricted pytest run stalled and was stopped; no full-suite pass is claimed for this investigation.

## 08:00 demo schedule — deployed and verified 6 November 2026

Supersedes the earlier note that timing changes were pending. The user explicitly
approved implementing the independent demo schedule while the real feed is blocked,
retaining prior displayed coverage as a provisional cutoff and rounding up.

Production now has 16 open demo shifts across 7, 14, 21 and 28 November 2026:
08:00–10:00, 10:00–12:00, 12:00–14:00 and 14:00–16:00 Europe/Amsterdam each day.
Each shift has three explicitly fictional assignments: 48 total using 24 identities.
Existing 18 demo parent names are reused subject to fairness; six extra fictional
placeholders have no account, credentials or email. The 19 existing accounts remain.
Fictional staffing is stored in separate demo_assignments records, never in real
parent confirmation or attendance records. API/UI distinguish fictional assignments
from confirmations. The closing time and all fixtures remain explicitly demo.

New Alembic revision d71e5082f906 creates the separate table (20 app tables now).
app/demo_schedule.py supplies the audited, idempotent one-time replacement.
Twelve old shifts and their invitations are preserved as cancelled history.
Production settings CANTEEN_OPENING_HOUR=8 and DEMO_STAFFING_ENABLED=true keep
future generation and worker runs consistent. Policy is 120 minutes / three places.
No real fixtures were imported; SPORTLINK credentials remain absent. No real mail
was sent: 36 cancellation messages were simulated, and all 72 outbox records remain
simulated. The app, users, source and schedule retain the demonstration boundary.

Private pre-change backup:
/home/datariotfc/private-backups/sdw-before-opening-0800-20261106T165602Z.dump
The existing signed-in hosting UI confirmed restart of site #1100302. Health and
both test logins pass after restart. Full suite: 49 passed (one existing Starlette
TestClient deprecation warning). Both JavaScript syntax checks passed. Production
and isolated fresh Alembic model comparisons passed. Final static hashes match the
published Dutch/English source. Mobile/desktop API responses match exactly, including
all block times, capacities, names/fictional flags and zero new real confirmations.
Worker run preserved all 16 shifts/48 assignments, proposed zero offers, and the
natural ten-minute heartbeat was verified afterward. Repeating the one-time update
returns already_applied. Hosted fairness check passed: minimum 14 days, no adjacent
matchday reuse, no identity used twice on the same day.

The English coordinator UI was visually checked on desktop and at 504px window
width with mobile navigation/cards; no physical device installation test was done.
A normal existing browser tab showed a few SDW programme entries, but no complete
current programme/cancellation state or repeatable feed was established. Do not claim
that real fixtures or an automated feed have been verified.

Full investigation and deployment evidence:
research/fixture-investigation-20261106.md

## Verified home programme — published 6 November 2026

This supersedes the earlier fixture-source blocker and provisional demo programme
notes above. A normal browser recovery re-established the official club URL and
captured its current public programme and detail pages. The manually reviewed
snapshot contains 31 real home fixtures for 7–8 November 2026: 26 on Saturday,
including one internal friendly, and five on Sunday. Opponent names, dates,
Amsterdam kickoffs, Spieringhorn pitch/venue mapping and the published absence of
cancellations were checked. The verification time is 6 November 2026 at 18:27
Europe/Amsterdam. This is historical snapshot coverage, not an automatic feed or
a claim that these dates remain upcoming.

`app/club_snapshot.py` imports reviewed manifests on stdin, validates the entire
snapshot before changing data and records provenance and audit history. Real
fixtures have source `club_snapshot` and are separate from fictional staffing.
The API and both languages display coverage, verification time and official match
links. The original demo fixtures remain as review/history and their old shifts
are cancelled without deleting accounts, assignments or invitations.

The imported weekend generated nine shifts: Saturday 08:00–18:00 and Sunday
08:00–16:00, in complete two-hour blocks. Each block has three explicitly fictional
parents (27 assignments), no fabricated real confirmations and no real email.
All 19 accounts were retained; the simulated outbox remained unchanged. A worker
run generated no duplicate shifts, invitations or messages. All hosted fixture
rows matched the reviewed manifest, and mobile/desktop payloads matched exactly.
The hosting UI confirmed restart; public health, test logins, roles, source asset
hashes and recent scheduled-worker heartbeat passed. Sixty isolated regression
tests and both JavaScript syntax checks passed. The desktop overview showed the
real first kickoff at 08:45. The final visual fixture-table check ended when the
computer-use tool could no longer establish Chrome's current URL; no restriction
was bypassed. Private source evidence and manifests stay under ignored `research/`.

Sportlink credentials remain absent. Future programme coverage needs another
verified snapshot or an authorized working feed; do not imply ongoing live sync.

## Git source publication — 11 November 2026

The user requested initial source publication to
https://github.com/TiagoCalvados/data-riot-fc. The current root instructions require
patch version bumps, a version prefix on each commit message, and commit/push for
each change. The application previously used FastAPI's implicit version 0.1.0;
the source release now explicitly defines 0.1.1 in `app/__init__.py` and uses that
same value in FastAPI. This Git publication does not deploy or restart the live app.
Secrets, local databases, research downloads, environments and backup archives stay
local and are excluded by `.gitignore`.

## Local Docker environment — source release 0.1.2, 11 November 2026

The user requested a complete local Docker test environment. Source now contains
a non-root runtime/test Dockerfile, a shared Compose service graph, separate local
and test overlays, and `scripts/dev.py` for cross-platform lifecycle commands.
PostgreSQL 17.11 persists only in the fixed local development project; each test
uses its own random project, fresh tmpfs PostgreSQL database and separate Mailpit.
Python 3.13.18, PostgreSQL and Mailpit 1.32.0 are pinned to verified image digests.
App and inbox default to loopback ports 8000 and 8025. Bootstrap waits for healthy
dependencies, migrates with Alembic and seeds fictional accounts idempotently;
app/worker wait for bootstrap completion. The worker runs existing jobs every
30 seconds locally, handles shutdown and exposes a successful-job heartbeat.

The default production mail path is unchanged. The explicit LOCAL_MAIL_CAPTURE
development option only accepts demo mode, HTTP loopback URLs/local cookies,
Mailpit or loopback SMTP on port 1025 without credentials, an example.invalid
sender and fictional example.invalid recipients. Captured outbox records remain
simulated; reply windows begin after local SMTP acceptance. Docker uses fictional
invitations rather than the deployment's passive demo staffing placeholders so
email/accept/decline can be exercised. Generated passwords/config live only in
ignored `.local/docker.env`; root/private production configuration is untouched.
The Docker context is source-allowlisted and contains no secrets, local data or
Git history. The wrapper refuses remote Docker endpoints, preserves local volumes
on normal startup/shutdown and requires an explicit destructive reset flag.

Validation: 75 host regression tests passed, both JavaScript syntax checks passed,
and both service graphs passed the real Docker Compose parser (including no test
host ports, isolated database name/storage and worker interval). The isolated
runner includes real PostgreSQL migration/seed-repeatability checks, HTTP login/
role/origin/cookie checks, captured Mailpit invitation/token/response flow and an
independent worker persistence check. Those container integrations have not run:
Docker Desktop 4.99.0 / Compose 5.7.0 are installed, but the dashboard explicitly
reports Virtual Machine Platform is not enabled and the engine is stopped.
Enabling that Windows feature requires administrator action and a Windows restart;
neither was performed silently. See dev/README.md for the exact remaining step.
No alwaysdata deployment or hosted database/email operation was performed.

## Docker checkout verification and local port fix — 11 November 2026

Version 0.1.3 fixes a startup problem found while running the new Docker stack on
Windows Docker Desktop. Services on the internal-only bridge were healthy and
internal HTTP smoke checks passed, but Docker left NetworkSettings.Ports empty
and neither published host URL was reachable.

The local Compose overlay now publishes app/Mailpit HTTP through a small TCP
gateway using the existing Python image. Only the gateway joins a normal bridge;
app, worker, PostgreSQL and Mailpit retain their internal-only network. Database
and SMTP ports remain unpublished. The gateway preserves streaming and half-closed
connections. `up` waits for gateway readiness, and both `up` and `smoke` now check
the actual loopback ports from the host.

The local stack is running at http://127.0.0.1:8000 with captured email UI at
http://127.0.0.1:8025. Both coordinator and parent login/dashboard/logout flows were
verified through the published app port. Docker credentials are separate from the
earlier SQLite demo; use `python scripts/dev.py credentials` to display only the
two test login passwords. Ignored `.local/docker.env` retains the generated config.

Validation: Compose config passes; 76 tests passed in the disposable container
project (one existing Starlette TestClient deprecation warning). Real PostgreSQL
bootstrap repeatability, Mailpit capture, an authenticated invitation response and
the independent worker heartbeat passed. Test resources were cleaned up by the
wrapper. The prior Python server was stopped to free port 8000. SQLite demo files
were retained. Hosted data and deployment were not involved.

## Individual local test mailboxes and Roundcube — 11 November 2026

Version 0.1.4 adds existing off-the-shelf containers, not a custom webmail app:
GreenMail 2.1.15 for SMTP/IMAP and Roundcube 1.7.6 Apache with the Elastic skin.
Both images are pinned by verified multi-platform digests. Mailpit remains the
message inspector and relays only example.invalid recipients to GreenMail. The
upstream GreenMail entrypoint is bypassed because it echoes credential options;
the official Java server runs directly, with IMAP password checks enabled.

Roundcube is at http://127.0.0.1:8080; app and inspector retain ports 8000/8025.
The six named fictional parent app accounts anna.test, bram.test, cem.test,
dana.test, els.test and finn.test have matching anna/bram/cem/dana/els/finn
@example.invalid mailboxes. Docker bootstrap adds them idempotently, retaining
all existing credentials and responses. Normal planning sends their invitations.
All original demo addresses plus beheer and kantine also have mailboxes (26 total).
Use `python scripts/dev.py credentials` for app and separate shared test-mail
passwords; no generated passwords are in source. Existing ignored Docker config
is upgraded by appending missing mail settings without resetting existing keys.

The user explicitly required internet isolation. Mailpit, GreenMail and Roundcube
join only Docker's internal network, with no SMTP/IMAP/API ports published. The
fixed-target gateway alone joins the host-access bridge and publishes the three
HTTP interfaces on 127.0.0.1. Runtime probes confirmed no default route, blocked
external IPv4/IPv6 connections and blocked external DNS. A wrong IMAP password
was rejected. There is no external SMTP relay or internet mail delivery.

All 78 container tests passed (one existing Starlette deprecation warning).
Real PostgreSQL bootstrap repeatability, Mailpit capture, private IMAP inboxes,
Roundcube login, mailbox isolation, authenticated invitation confirmation and the
independent worker heartbeat passed. The disposable test stack was cleaned up.
In the browser, Anna's 21 November 12:00-14:00 invitation was confirmed; her other
invitation remains pending. Roundcube sent an Anna-to-Bram message and Bram's
inbox displayed it. The browser is left with Bram's inbox and the app logged out.
Ignored screenshots: .local/test-webmail.jpg and .local/mail-confirmation.jpg.

Mailpit and GreenMail messages are temporary across mail-container recreation or
stops. App invitation/audit data, passwords and Roundcube preferences persist in
their existing private config/volumes. This change does not deploy hosted code.

## Docker startup after WSL installation — 11 November 2026

Pulled and reviewed upstream releases 0.1.3 (loopback HTTP gateway) and 0.1.4
(GreenMail, Roundcube and named fictional test parents), through commit 712ff31.
WSL 3.0.5.0 is now installed and Docker Desktop's Linux engine runs successfully.

Version 0.1.5 fixes this PC's remaining build failures. AVG intercepts package
HTTPS using its trusted Windows public CA, which was exported to ignored
`.local/build-ca.pem`. The wrapper selects matching optional local/test Compose
overlays and passes this file as a BuildKit secret to the two pip installation
steps. TLS certificate verification stays enabled. The CA is not copied into an
image or installed in runtime trust; its absence was verified in the running app.
Machines without that local file continue using normal public CA verification.

The test-stage root Compose wildcard also attempted to scan an unreadable host
`.pytest_cache` directory despite the source allowlist. Explicit named COPY inputs
resolve that failure; pytest caches now have an explicit Docker ignore rule too.
The restricted host pytest attempt was stopped after stalling; container results
below are the completed verification for this change.

Validation: all 79 container tests passed, with the existing Starlette TestClient
deprecation warning. Repeated PostgreSQL bootstrap, Mailpit SMTP capture, private
IMAP delivery/isolation, Roundcube login, authenticated invitation confirmation
and independent worker advancement all passed. The temporary test project and
its images were cleaned up. Interactive smoke checks passed, including host
HTTP on app 8000, Mailpit 8025 and Roundcube 8080, both roles, languages, origins,
cookies and recent job status. All seven persistent services are healthy and
bootstrap exited successfully. Local data/passwords were preserved; configuration
was extended with the upstream mail defaults. Credentials remain available via
`python scripts/dev.py credentials`. No hosted deployment was performed.

## Local PostgreSQL web UI — 11 November 2026

Version 0.1.6 adds the official Adminer 6.3.0 standalone image, pinned by verified
multi-platform digest, only to the interactive Compose overlay. It uses the
existing PostgreSQL credentials: system PostgreSQL, server db, user sdw, database
sdw_local; the password stays in LOCAL_DB_PASSWORD in ignored .local/docker.env.
No extra account/password is created and the credentials command prints connection
details plus the password's file location without exposing the database secret.

Adminer is at http://127.0.0.1:8081. The local gateway forwards HTTP to its internal
port 8080. Adminer joins only the internal network, has a read-only filesystem and
temporary session storage, and publishes no direct ports. PostgreSQL port 5432
remains unpublished. Actual Adminer-container probes confirmed no default route,
blocked external IPv4/IPv6 and blocked external DNS. The existing app/mail URLs
and stored credentials are retained. DB_UI_PORT is appended to older config; all
four browser ports are checked for collisions and verified from the host.

The browser successfully logged in and displayed all 21 public-schema tables
(20 app tables plus Alembic). It remains open as a deliverable. No database rows
were edited in this check. Screenshot: ignored .local/postgresql-ui.jpg.
All 79 regression tests and the existing isolated PostgreSQL/mail/webmail/worker
integration flow passed; temporary test resources were cleaned up. No Adminer is
started in that disposable stack. This change affects local development only.
The other editor's 0.1.5 build-CA support was integrated and preserved before the
final 0.1.6 build/test run; machines without the optional CA file still build normally.
