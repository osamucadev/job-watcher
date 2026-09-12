# Job Watcher

Job Watcher is a self-hosted dashboard that watches company career pages and collects new job postings in one place. Instead of opening dozens of career pages by hand, you check one dashboard.

The first supported source is InHire, read directly from its public API. Other platforms can be added later through the same adapter pattern.

## Running locally

```bash
git clone https://github.com/osamucadev/job-watcher.git
cd job-watcher
docker compose up -d --build
```

Open [http://localhost:17843](http://localhost:17843). The first check runs automatically and builds the baseline in about ten seconds; refresh the page to see jobs come in.

No `.env` file is required to get started. Copy `.env.example` to `.env` only if you want to change the host port or timezone:

| Variable | Default | Purpose |
| --- | --- | --- |
| `JOB_WATCHER_PORT` | `17843` | Host port for the dashboard |
| `JOB_WATCHER_TIMEZONE` | `America/Sao_Paulo` | Timezone for the daily schedule |

Data lives in the `job-watcher-data` Docker volume. Never run `docker compose down -v`, it deletes the volume and all job history.

## What it does

- Monitors career pages from multiple companies through their InHire API
- Runs automatic checks every day at 09:00, 12:00, 15:00 and 18:00 (configurable timezone), with a catch-up check if the app was offline
- Detects new job postings and archives jobs that disappear from a source, without ever deleting history
- Lists all active jobs, paginated
- Highlights jobs that match your interest keywords, editable from the Settings page
- Lets you mark a job as already applied, or archive it manually with a reason and note
- Keeps a visited indicator once you have opened a job link
- Shows an activity page with live progress of a running check, check history, and the last result per company
- Supports a manual "check now" action at any time
- English and Brazilian Portuguese interface, switchable per browser

## Monitored companies

The project ships with an initial set of monitored companies, seeded on first start.

To add your own, open the **Companies** page in the dashboard and add a career page URL. No code changes needed for InHire sources.

If you prefer to edit the initial list directly, it lives in [`app/database.py`](app/database.py) as `SEED_COMPANIES`.

## Screenshots

<table>
<tr>
<td><img src="docs/images/job-watcher-overview.png" width="400" alt="Overview"></td>
<td><img src="docs/images/job-watcher-jobs.png" width="400" alt="All jobs"></td>
</tr>
<tr>
<td><img src="docs/images/job-watcher-highlights.png" width="400" alt="Highlights"></td>
<td><img src="docs/images/job-watcher-settings.png" width="400" alt="Settings"></td>
</tr>
<tr>
<td colspan="2"><img src="docs/images/job-watcher-activity.png" width="400" alt="Activity"></td>
</tr>
</table>

## More documentation

See [AGENTS.md](AGENTS.md) for the product and technical guidelines behind this project.

This README is also available in [Brazilian Portuguese](docs/README.pt-BR.md).
