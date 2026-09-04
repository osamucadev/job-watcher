# Job Watcher

Job Watcher is a local web dashboard that monitors company career pages and identifies newly published opportunities. It is designed for developers who want a calm, private, and visually polished way to follow multiple job sources from their own computer.

The first supported platform will be InHire. The project will be structured so that other job platforms can be added later through independent source adapters.

## Status

The first functional version is available. It includes the InHire collector, persistent history, scheduled checks, a bilingual local dashboard, company management, profile highlights, and job archiving.

## Experience

- Local browser based dashboard
- English interface by default
- Brazilian Portuguese interface option
- Per browser language persistence through localStorage
- Overview of new and highlighted opportunities
- Complete active job listing
- Manual job archiving and restoration
- Automatic archiving when a job disappears from its source
- Dedicated archive with indefinite history
- Company source management from the interface
- Direct links that open job posts in a new browser tab
- Editable keywords for software development, AI, mobile, backend, frontend, full stack, and technical leadership roles

## Schedule

The monitor is planned to run every day in the `America/Sao_Paulo` timezone at:

- 09:00
- 12:00
- 15:00
- 18:00

Weekends and holidays are included. If the computer is unavailable during one or more scheduled checks, Job Watcher will perform one catch up check when the service starts again.

The first successful collection creates the baseline. Jobs already present during that collection will not be marked as new.

## Technology

- Python
- FastAPI
- Server rendered HTML
- SQLite
- Playwright for JavaScript rendered career pages
- Docker Compose

The project intends to avoid a frontend JavaScript toolchain. If JavaScript dependencies become necessary, pnpm will be used.

## Visual direction

The interface will draw inspiration from the Windows 8 Metro design language:

- Square corners and rectangular tiles
- Flat, high contrast color areas
- Dark navy and purple foundation
- Yellow primary accent
- Strong typography
- Minimal decoration and restrained motion

The logo and favicon will use an original geometric symbol. They will not use initials or a letter based monogram.

## Local deployment

The application runs with Docker Compose on Ubuntu and restarts automatically with Docker. It binds only to the local computer by default.

### Start

```bash
docker compose up -d --build
```

Open [http://localhost:17843](http://localhost:17843) in a browser.

The first collection starts automatically and creates the baseline. With 30 sources, it can take a few minutes. Refresh the dashboard to see collected jobs.

### Stop

```bash
docker compose down
```

The database remains in the `job-watcher-data` Docker volume.

### Configuration

Copy `.env.example` to `.env` only when you want to change the local port or timezone.

```dotenv
JOB_WATCHER_PORT=17843
JOB_WATCHER_TIMEZONE=America/Sao_Paulo
```

The interface language is independent for each browser profile and is stored only in browser localStorage.

## Data behavior

- The first successful check for each company creates its baseline.
- New jobs are marked during the check in which they are discovered.
- Jobs missing from a successful source collection are archived, never deleted.
- Jobs that return after source archiving are restored and marked as reopened.
- Manually archived jobs remain archived while their source stays active.
- Removing a company stops monitoring and archives its active jobs while preserving history.

## Development

Run the test suite with:

```bash
python -m unittest discover -v
```

The application intentionally uses one server worker because the scheduler runs inside the web process. This prevents duplicate scheduled checks.
