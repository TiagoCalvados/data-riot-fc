# Local Docker environment

The local stack is independent of alwaysdata, the root `.env`, the local SQLite
demo, SSH keys and all hosted data. It uses fictional fixtures and parents only.

## Prerequisites and first start

Install Python 3.11+ for the small cross-platform command wrapper (no host Python
packages are required). Install a Docker Linux engine and Docker Compose 2.24+.
On Windows, use [Docker Desktop's official installation instructions](https://docs.docker.com/desktop/setup/install/windows-install/)
and its WSL 2 backend. Docker Desktop may need a one-time administrator WSL setup,
license acceptance and a Windows restart. The project never changes Windows features,
reboots, installs software or accepts licenses for you.

Run these commands from the project root, identically in PowerShell or a Unix shell:

```text
python scripts/dev.py doctor
python scripts/dev.py init
python scripts/dev.py up
python scripts/dev.py credentials
```

On Windows, `py -3` can replace `python`. `up` also creates missing local config,
builds the image, starts services and waits for successful app/worker health checks.
The wrapper finds Docker Desktop's standard per-user/all-user binary paths even
when the current terminal has not refreshed its PATH.

Open **http://127.0.0.1:8000** for the app and **http://127.0.0.1:8025** for captured
email. Use that exact app hostname: the app checks request origins against BASE_URL.
The coordinator is `beheer.test`; the parent is `ouder.test`. Random passwords are
shown only by the explicit `credentials` command. All other seeded accounts and
recipients are fictional. Credentials are stable across restarts/rebuilds.

For different ports, run `init --app-port 8080 --mail-port 8026` before the first start.
After initialization, edit only APP_PORT/MAIL_PORT in ignored `.local/docker.env`,
then run `up` again. Do not change stored database/application/login secrets for an
existing volume: initialization deliberately never resets accounts or passwords.
The root `.env` is not read by Compose; the wrapper always supplies `--env-file`.
The wrapper also refuses remote Docker endpoints/contexts: select a local Desktop
or local Linux socket rather than a production/SSH Docker context.

## Services and lifecycle

| Service | Purpose |
| --- | --- |
| db | PostgreSQL 17.11, readiness check and project-scoped persistent dev volume |
| mailpit | Mailpit 1.32.0, capture-only SMTP on the internal network and loopback UI |
| bootstrap | One-shot Alembic migration, idempotent fictional seed and first job |
| app | Python 3.13.18 / FastAPI as UID 10001, read-only filesystem and HTTP health probe |
| worker | Existing `run_job` every 30 seconds locally; successful-job heartbeat and graceful shutdown |
| gateway | Local-only TCP forwarding for app/Mailpit HTTP; the only service on a host-access bridge |
| tests | Separate test image and disposable PostgreSQL/Mailpit project; no host ports |

Compose waits for PostgreSQL/Mailpit health, then successful bootstrap completion,
then starts app and worker, followed by the local HTTP gateway. Migrations and seed are not run in every web worker.
Existing PostgreSQL advisory locks still serialize jobs and coordinator changes.
Normal startup and shutdown retain the PostgreSQL volume. The Mailpit inbox is
deliberately temporary and clears when its container is replaced/stopped; delivered
invitation/response/audit history remains in PostgreSQL.

```text
python scripts/dev.py status
python scripts/dev.py logs
python scripts/dev.py down
python scripts/dev.py up
python scripts/dev.py rebuild
python scripts/dev.py smoke
python scripts/dev.py test
```

`logs` follows the last 100 lines (Ctrl+C exits log viewing). `rebuild` pulls the
specified immutable image digests and rebuilds without erasing the database. Review
and update the version/digest pairs explicitly when upgrading dependencies. Source changes are
reproducibly copied into images; there are no host-code/credential directory mounts.
`up` and `smoke` verify both published ports from the host, so healthy containers
alone cannot hide a missing browser connection. `smoke` also checks the interactive stack's HTTP, language pages, cookies, same-origin
checks, both roles and recent worker status. It does not confirm or delete duties.
`config` performs Compose's validation without printing interpolated secrets.

## Mail and invitation testing

The default Docker setup deliberately keeps DEMO_MODE=true and
DEMO_STAFFING_ENABLED=false. This exercises the existing fictional invitation/reply
workflow rather than filling every place with non-interactive staffing placeholders.
The UI explicitly labels local captured email; fictional fixtures/parents remain
marked, and SMTP outbox records remain `simulated`.

LOCAL_MAIL_CAPTURE=true is an explicit development-only transport. Startup rejects
it unless demo mode is enabled, cookies are local HTTP cookies, BASE_URL is HTTP
loopback, SMTP is `mailpit`/loopback on port 1025 without credentials and the sender
is under example.invalid. Only demo users with example.invalid recipient addresses
can enter that transport. Production SMTP's verified TLS/authentication and test
address blocking remain unchanged when the option is false (the default).

Mailpit has no relay configuration, no SMTP host port, and no external network route.
Open the inbox, find the invitation to `demo0@example.invalid`, follow its local link,
sign in as `ouder.test` and explicitly accept/decline. GET never accepts a duty. The
usual 48-hour maximum reply period begins only after Mailpit accepts the message;
decline/expiry/fairness/spacing behavior remains the existing business logic.

## Isolated tests and destructive reset

`python scripts/dev.py test` creates a random `sdw-kantine-test-...` Compose project
with a fresh tmpfs PostgreSQL database named `sdw_test`, fresh credentials, a separate
Mailpit inbox and no published ports. It runs the entire unit suite, repeats real
PostgreSQL migration/bootstrap twice, checks login/roles/cookies/origins, finds a
captured invitation through Mailpit's API, follows its authenticated link, submits
a response, and waits for the independent worker to advance without replacing
shifts. The response test refuses to run against `sdw_local` or another database.
A `finally` cleanup removes only that random test project, volumes and local image
tags. It cannot erase the interactive development database.

Reset is never implicit. To erase **only this project's local PostgreSQL volume**:

```text
python scripts/dev.py reset --confirm-delete-local-data
python scripts/dev.py up
```

Reset retains `.local/docker.env`, so a fresh fictional database receives the same
local test login passwords. It does not prune Docker globally or touch alwaysdata.

## Files, safety and troubleshooting

- `compose.yaml`: shared service graph; `compose.local.yaml`: loopback ports and
  persistent dev storage; `compose.test.yaml`: disposable test storage/runner.
- `Dockerfile`: non-root runtime and separate test target, pinned Python/dependencies.
- `.dockerignore`: allowlisted source only. `.local`, `.env`, private credentials,
  Git history, research downloads, databases and backups cannot enter build context.
- `.local/docker.env` is generated/ignored; do not share it or the output of raw
  `docker compose config`, which contains interpolated local secrets.
- Port busy: stop the other local service or choose different local ports; the app
  and inbox are bound to 127.0.0.1, never all host interfaces by default.
- Docker does not publish ports for containers attached only to an internal network.
  The local gateway joins a separate normal bridge and forwards only app/Mailpit
  HTTP. App, worker, PostgreSQL and Mailpit remain on the internal network without
  an external route; SMTP and database ports are not published. The gateway uses
  the existing Python runtime image and preserves streaming/connection upgrades.
- Startup failure: `doctor`, `status`, then `logs`; fix the failing dependency before
  retrying `up`. A failed migration prevents app/worker from starting.
- An old Mailpit invitation may expire. Check the parent dashboard; the coordinator
  can update planning normally. No bootstrap operation resets existing responses.
- If an interrupted test leaves a random project behind, inspect `docker compose ls`
  and remove only that named test project; never use a global prune as a reset.

Original authoring-machine status on 11 November 2026 (historical, not a diagnosis
of other checkouts): Docker and WSL were initially absent.
Docker Desktop 4.99.0 and Compose 5.7.0 are now installed. Both local/test service
graphs pass the actual Compose parser, all 75 host tests pass, and JavaScript syntax
checks pass. The three image tags/digests were checked against Docker Hub. Docker
Desktop reports **Virtual Machine Platform is not enabled** and its Linux engine
is stopped; no container build or PostgreSQL/Mailpit integration run is claimed.

On this PC the remaining setup requires an administrator Windows feature change
and a Windows restart, which the project does not perform. Save your work, then in
administrator PowerShell run:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart
```

Restart Windows when ready, open Docker Desktop, complete any first-run prompts,
then run `python scripts/dev.py doctor`, `python scripts/dev.py up` and
`python scripts/dev.py test`. If Docker then reports that WSL itself needs installing
or updating, follow its official WSL setup instructions before retrying.

Checkout verification on 11 November 2026 with version 0.1.3: the Linux engine
started successfully, the local stack and host gateway are healthy, and both
browser-facing login flows pass. All 76 container tests passed, followed by the
isolated PostgreSQL/Mailpit invitation-response and worker-heartbeat checks. The
disposable test project was removed; the interactive local stack remains running.

References: [Compose startup conditions](https://docs.docker.com/compose/how-tos/startup-order/),
[Mailpit Docker/readiness](https://mailpit.axllent.org/docs/install/docker/),
[Mailpit runtime options](https://mailpit.axllent.org/docs/configuration/runtime-options/),
[PostgreSQL image](https://hub.docker.com/_/postgres), [Python image](https://hub.docker.com/_/python).
