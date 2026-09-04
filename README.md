# Job Watcher

Job Watcher is a local web dashboard that monitors company career pages and identifies newly published opportunities. It is designed for developers who want a calm, private, and visually polished way to follow multiple job sources from their own computer.

The first supported platform will be InHire. The project will be structured so that other job platforms can be added later through independent source adapters.

## Status

Job Watcher is currently in the product definition stage. No application implementation has started yet.

## Planned experience

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

## Planned technology

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

The application will run with Docker Compose on Ubuntu and restart automatically with Docker. A high, uncommon host port will be selected after checking which ports are already in use.

Setup and usage instructions will be added when the first working version is implemented.
