# Contributing

Thanks for taking a look at Job Watcher. This is a small self-hosted project, so the process is kept simple.

## Getting set up

- Python 3.12 or newer. No headless browser and no Node toolchain are required.
- Install dependencies:

  ```bash
  pip install -r requirements.txt
  ```

- Run the app without Docker (creates and uses `data/job-watcher.db`):

  ```bash
  uvicorn app.main:app --reload
  ```

- Run the test suite before opening a pull request:

  ```bash
  python -m unittest discover -v
  ```

## Guidelines

The project follows the conventions described in [AGENTS.md](AGENTS.md): stack choices, visual direction, monitoring behavior, and internationalization rules. Read it before making non trivial changes, especially around collection and scheduling logic.

A few points worth repeating:

- Prefer Python, FastAPI, server rendered HTML, CSS, and SQLite. Avoid adding a frontend framework or a headless browser dependency.
- If a JavaScript dependency ever becomes necessary, use pnpm, never npm.
- Add schema changes as additive migrations. Do not rewrite or reseed existing data.
- Keep user facing copy natural in both English and Brazilian Portuguese.
- Do not use the em dash character anywhere in the project: code, docs, commit messages, or interface copy.

## Adding a company source

New InHire company sources can be added directly from the Companies page in the running app, no code change required. See the "Monitored companies" section in the [README](README.md) for details.

## Pull requests

- Keep changes focused; small, single purpose pull requests are easier to review.
- Include or update tests for behavior changes.
- Describe what changed and why in the pull request description.

## Reporting issues

Open a GitHub issue with steps to reproduce, what you expected, and what happened instead. For collection failures, include the company source URL if possible (without exposing anything private).
