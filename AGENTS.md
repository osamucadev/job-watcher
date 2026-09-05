# Job Watcher Agent Guidelines

## Communication

- Never use the em dash character in source code, documentation, interface copy, comments, commits, or messages created for this project.
- Write all project documentation in English.
- Keep user facing copy concise and natural in both supported languages.

## Product

- The product name is Job Watcher.
- Do not abbreviate the product as "JW" and do not use a JW monogram in its identity.
- The initial source integration is InHire, but the architecture must allow additional job platforms later.
- The application is a local web dashboard designed to run continuously with Docker on Ubuntu.

## Technology

- Prefer Python, FastAPI, server rendered HTML, CSS, and SQLite.
- Avoid custom JavaScript unless it materially improves the experience.
- If JavaScript dependencies become necessary, use pnpm. Do not use npm.
- Do not introduce a frontend framework without a clear product need.

## Interface and visual identity

- Follow a Metro inspired visual direction, influenced by Windows 8.
- Prefer square corners, rectangular tiles, strong typography, and flat color blocks.
- Do not use rounded cards, pill shaped controls, or excessive shadows.
- Use a dark navy and purple foundation with yellow as the primary accent.
- Design for desktop first while preserving basic mobile usability.
- Create an original logo and favicon without letters or monograms.

## Internationalization

- Support English and Brazilian Portuguese.
- English is the default language.
- Store the selected language in browser localStorage only.
- Language preferences must remain independent across browsers and browser profiles.
- Do not store the language preference in SQLite.

## Monitoring behavior

- Run scheduled checks every day at 09:00, 12:00, 15:00, and 18:00 in the America/Sao_Paulo timezone.
- Include weekends and holidays.
- When the service starts after missing one or more scheduled checks, run one catch up check.
- Treat the first successful collection as the baseline. Existing jobs are not new jobs.
- Preserve job history indefinitely.
- Automatically archive jobs that disappear from their source.
- Support manual archive and restore actions.
- Record whether a job was archived manually or because it disappeared.
- If a source archived job reappears, restore it and mark it as reopened.
- Never delete a job merely because it is no longer listed by the source.

## Initial experience

- Provide pages for overview, all jobs, highlighted jobs, archived jobs, companies, settings, and activity.
- The activity page shows the live progress of a running check, recent check history, and the last result per company. It states plainly that the rest of the app stays usable during a check.
- Allow users to add, pause, edit, and remove company source links.
- Open source job links in a new browser tab.
- Do not add filtering in the initial version.
- Highlight roles related to full stack, backend, frontend, mobile, AI, software development, and technical leadership.
- Make highlight keywords editable from the interface.

## Deployment

- Use Docker Compose and configure the application service to restart automatically.
- Select a high, uncommon host port only after checking ports already in use.
- Keep persistent application data in a Docker volume or an explicitly documented local directory.
