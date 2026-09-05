# Job Watcher

Job Watcher is a local web dashboard that monitors company career pages and surfaces newly published opportunities. It is built for developers who want a calm, private, and visually polished way to follow many job sources from their own computer.

The first supported platform is InHire. The application is structured so that other job platforms can be added later through independent source adapters.

## Interface preview

![Job Watcher highlighted jobs dashboard](docs/images/job-watcher-highlighted.png)

## Status

Job Watcher is functional and in daily use. It collects from the InHire public API, keeps permanent job history, runs scheduled checks, and serves a bilingual dashboard with company management, editable profile highlights, paginated listings, visited tracking, an activity page, and manual archiving with reasons and notes.

## Pages

- **Overview**: new and highlighted opportunities at a glance
- **All jobs**: every active opportunity, paginated
- **Highlights**: active jobs matched against your interest keywords
- **Archive**: jobs you archived or that were removed from their source, kept indefinitely
- **Companies**: add, pause, and remove source links
- **Settings**: edit the highlight keywords
- **Activity**: live progress of a running check, check history, and the last result per company

## Experience

- Local browser based dashboard, bound to the local computer by default
- English interface by default, Brazilian Portuguese option
- Language choice persists per browser through localStorage and is never stored in the database
- One click "Applied" action that archives a job with the applied reason
- Manual job archiving and restoration
- Archive reasons shown as one click chips, with an optional personal note
- A short action modal right after opening a job, offering Applied, Archive, or keep it active
- Toast confirmations with an undo option after archiving or applying
- Visited indicator once a job link has been opened, kept in the database
- Highlighted border on the job most recently opened, kept in the browser
- Automatic archiving when a job disappears from a confirmed source response
- Company source management from the interface
- Direct links that open job posts in a new browser tab
- Editable keywords for software development, AI, mobile, backend, frontend, full stack, and technical leadership roles
- Short, flat styled transitions for modals, toasts, and list changes, disabled under reduced motion preferences

## Collection

Job Watcher reads listings straight from the InHire public API instead of rendering career pages in a browser. For each company source it calls:

```http
GET https://api.inhire.app/job-posts/public/pages/lean
Content-Type: application/json
X-Tenant: <tenant>
```

The tenant is taken from the first label of the source host, so `https://lyncas.inhire.app/vagas` uses the tenant `lyncas`. The career page is taken from the path: `/vagas` means the default career page, while `/octadesk/vagas` or `/supero/vagas` select the `octadesk` and `supero` career pages. Results are filtered by that career page, so a shared tenant only reports the jobs that belong to the registered source.

Each listing entry gives a stable `jobId` used as the external identifier, a `displayName` used as the title, and a link back to the public job post. Collection uses a small concurrency limit, short timeouts, and a brief retry for transient failures only (timeouts, connection errors, HTTP 429, and HTTP 5xx). Permanent HTTP errors are not retried.

A failed or unconfirmed collection never archives a company's jobs. Jobs are archived only when the API returns a valid response for the correct career page and a job is absent from it.

This design removed the previous Playwright and Chromium dependency: a full scan of about 30 sources finishes in roughly ten seconds, and the Docker image is around 250 MB instead of several gigabytes.

## Schedule

Job Watcher runs scheduled checks every day, including weekends and holidays, in the configured timezone (`America/Sao_Paulo` by default) at:

- 09:00
- 12:00
- 15:00
- 18:00

If the computer is off during one or more windows, Job Watcher runs a single catch up check when the service starts again.

## Activity page

The activity page (`/activity`) reports what a check is doing while it runs:

- Overall progress as companies checked out of the total, with a per company state of waiting, collecting, done, or failed.
- A plain statement that every other page keeps working during a check. Only starting a second manual check is blocked until the current one finishes.
- A stalled warning when a running check has not updated its heartbeat for a few minutes. The next scheduled check starts a fresh run.
- History of recent checks with duration, status, and job counts.
- The last result and last check time for each company source.

While a check is running the page refreshes itself every few seconds with a plain meta refresh, so it needs no custom JavaScript. A leftover running check from a process that stopped mid run is closed out as failed on the next start.

## Data behavior

- The first successful check for each company creates its baseline. Existing jobs at that point are not new jobs.
- New jobs are marked during the check in which they are discovered.
- Jobs missing from a confirmed source response are archived, never deleted.
- A failed collection for one company never archives that company's jobs.
- Jobs that return after source archiving are restored and marked as reopened.
- Manually archived jobs record a reason and may include a personal note.
- Manual reasons include already applied, no interest, work arrangement, requirements, compensation, closed applications, and other.
- Manually archived jobs remain archived while their source stays active.
- Removing a company stops monitoring and archives its active jobs while preserving history.
- The first and last time a job link is opened are recorded in SQLite.
- Undoing an archive restores the job without marking it as reopened. That label stays reserved for jobs the source itself brings back.

## Technology

- Python and FastAPI
- Server rendered HTML with Jinja2, plain CSS, and a small amount of vanilla JavaScript for modals, toasts, and language switching
- SQLite for storage
- httpx for the InHire public API
- APScheduler for the daily schedule
- Docker Compose for deployment

There is no frontend build step and no headless browser. If a JavaScript dependency ever becomes necessary, pnpm is used, never npm.

## Visual direction

The interface draws from the Windows 8 Metro design language:

- Square corners and rectangular tiles
- Flat, high contrast color areas
- Light neutral canvas and white panels
- Teal, turquoise, pink, coral, yellow, and purple flat color blocks
- Strong typography
- Minimal decoration and restrained motion

The logo and favicon use three geometric job rows with distinct status blocks. The mark represents monitored listings and changing job states without using initials or a letter based monogram.

## Local deployment

The application runs with Docker Compose on Ubuntu and restarts automatically with Docker. It binds only to the local computer by default.

### Start

```bash
docker compose up -d --build
```

Open [http://localhost:17843](http://localhost:17843) in a browser.

The first collection starts automatically and creates the baseline. It finishes in about ten seconds. Refresh the dashboard to see collected jobs.

### Stop

```bash
docker compose down
```

The database remains in the `job-watcher-data` Docker volume. Never pass `-v` to `docker compose down`; that deletes the volume and all history.

### Configuration

Copy `.env.example` to `.env` only when you want to change the local port or timezone:

| Variable | Default | Purpose |
| --- | --- | --- |
| `JOB_WATCHER_PORT` | `17843` | Host port for the dashboard |
| `JOB_WATCHER_TIMEZONE` | `America/Sao_Paulo` | Timezone for the daily schedule |

Inside the container the data directory is fixed to `/data` (the `job-watcher-data` volume) through `JOB_WATCHER_DATA_DIR`. The application also honors `JOB_WATCHER_DATABASE` for a full database path; neither normally needs changing.

## Development

- Python 3.12 or newer. No headless browser and no Node toolchain are required.
- Install dependencies:

  ```bash
  pip install -r requirements.txt
  ```

- Run the test suite:

  ```bash
  python -m unittest discover -v
  ```

- Run the app without Docker (creates and uses `data/job-watcher.db`):

  ```bash
  uvicorn app.main:app --reload
  ```

The application intentionally uses one server worker because the scheduler runs inside the web process. This prevents duplicate scheduled checks.

## Project layout

| Path | Responsibility |
| --- | --- |
| `app/main.py` | Routes and page rendering |
| `app/services/inhire.py` | InHire public API client: tenant and career page parsing, retries |
| `app/services/monitor.py` | Check run orchestration and baseline, new, archive, reopen logic |
| `app/services/scheduler.py` | Daily schedule and catch up check |
| `app/services/pagination.py` | Page number sequence for listings |
| `app/database.py` | Schema, migrations, and seed companies |
| `app/templates/`, `app/static/` | Server rendered UI |
| `tests/` | Unit tests, run with `unittest` |
