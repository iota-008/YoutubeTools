# YouTube Tools Hub

YouTube Tools Hub is a Flask-based multi-tool workspace for creators. It provides transcript extraction, thumbnail utilities, stream quality selection, SEO suggestions, channel audit reports, and idea generation from a single dashboard.

## Feature overview

- Transcript extraction with language selection: Fetch captions by selected language with controlled fallback behavior when unavailable.
- Stream quality selector: Lists available progressive formats and lets users open/download selected media streams.
- Thumbnail toolkit: Resolves common thumbnail resolutions and supports direct thumbnail download.
- SEO helper: Produces title/description/hashtag suggestions from available video metadata and transcript context.
- Channel audit report: Summarizes sampled channel videos (keywords, title patterns, average metrics, and recommendations).
- Idea generator: Generates structured idea cards (title, angle, CTA) from niche/audience/goal inputs.
- Run history tracking: Stores tool runs in DB (`ToolRun`) and exposes both UI and JSON history endpoints.
- Resilient data sourcing: Uses multiple providers/fallbacks (`pytubefix`, transcript API, `yt-dlp`, oEmbed/feed) to reduce failure rates.

## Architecture

### High-level flow

1. User opens a tool route (`/tools/...`) and submits a YouTube URL or input parameters.
2. App extracts normalized video/channel identifiers.
3. Tool logic resolves metadata/captions/streams using primary provider + fallback providers.
4. Result is rendered in UI and a run record is stored in DB (`ToolRun`).

### Reliability strategy

- Multiple data source fallbacks (pytubefix/pytube, YouTube transcript API, yt-dlp, oEmbed/RSS where applicable).
- Graceful warnings for partial data.
- Stateless request handling (no long-lived in-memory state needed between requests).

### Deployment topology

- Reverse proxy: Traefik on external Docker network `web`.
- App stack: `web` + `db` from compose.
- CI/CD: GitHub Actions SSH deployment.
- VM file strategy:
  - Source clone in `/opt/projects/yt-tools`
  - Stack env/compose can live in `/home/ubuntu/stacks/yt-tools`

## Implemented tools

- Transcript Extractor
- Video Stream Selector
- Thumbnail Tool
- Title & Description Optimizer
- Channel Audit
- Idea Generator

## Technology stack

- Python 3.12
- Flask 3.x + Jinja2
- Flask-SQLAlchemy
- Flask-Talisman
- Gunicorn
- pytubefix + pytube
- youtube-transcript-api
- yt-dlp
- requests
- PostgreSQL 16 (prod)

## Repository layout

- `app.py`: routes + tool implementations + DB model + fallback logic
- `templates/`: tool pages and base layout
- `static/`: css/js/favicon/robots/sitemap
- `docker-compose.yml`: production-oriented compose stack for VM deployment
- `.github/workflows/deploy.yml`: CI deploy automation
- `.env.production.example`: production env template

## Environment variables

Core:

- `SECRET_KEY`
- `FORCE_HTTPS` (`true` in production behind TLS)
- `APP_DOMAIN`
- `DATABASE_URL`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

DB URI example:

`postgresql+psycopg://youtubetools:<password>@db:5432/youtubetools`

Use URL-safe passwords for `DATABASE_URL` or URL-encode reserved characters.

## Local development

1. Install deps: `pip install -r requirements.txt`
2. Create `.env` (optional):

```env
SECRET_KEY=replace-with-random-secret
FORCE_HTTPS=false
DATABASE_URL=sqlite:///youtube_tools.db
```

3. Run: `flask --app app run --debug`
4. Open: `http://127.0.0.1:5000`

## Production deployment (VM + Traefik)

### VM prerequisites

- Docker + Compose plugin installed
- Shared proxy network: `docker network create web`

### GitHub repository variables

- `VM_USER`
- `DEPLOY_PATH` (example `/opt/projects/yt-tools`)
- `COMPOSE_FILE` (optional)
- `ENV_FILE` (optional)

### GitHub repository secrets

- `VM_HOST`
- `SSH_PRIVATE_KEY`
- `VM_HOST_KEY` (recommended)

### Deployment behavior (current workflow)

- Triggers on push to `master`/`main` and manual dispatch.
- Resolves compose/env from variable path, then stack dir, then deploy dir.
- Fresh clones source into `DEPLOY_PATH`.
- Copies resolved env file into `DEPLOY_PATH/.env.production` for compose compatibility.
- Uses `docker compose --project-directory $DEPLOY_PATH ...`.

## Operational endpoints

- `GET /health`: liveness check
- `GET /history`: rendered run history
- `GET /api/history`: JSON run history

## Security and compliance notes

- Keep `.env` and `.flaskenv` out of git.
- Rotate any secrets if they were ever committed.
- Respect YouTube Terms and applicable content policies.
- Use this project for metadata/transcript/tooling workflows, not unauthorized redistribution.

## Troubleshooting

### Wrong language transcript returned

Language selection is strict with fallback logic; if selected language isn’t accessible, tool returns unavailable/fallback warning instead of unrelated language.

### `env file .../.env.production not found`

Ensure stack env exists and workflow has permissions. Current workflow syncs env file into deploy path before compose operations.

### PostgreSQL connection issues

- Verify `POSTGRES_*` values and `DATABASE_URL` match.
- If password changed after DB volume init, recreate DB volume and redeploy.

## Screenshots

Core flow  
![Home Page](screenshots/1.png?raw=true)
![Enter Video Link](screenshots/2.png?raw=true)
![Get Transcript](screenshots/3.png?raw=true)
![Download video](screenshots/4.png?raw=true)
![Download thumbnail](screenshots/5.png?raw=true)
![Download thumbnail 2](screenshots/6.png?raw=true)

Extended screens  
![Dashboard overview](screenshots/screen-07-dashboard-overview.png?raw=true)
![Transcript tool page](screenshots/screen-08-transcript-tool-page.png?raw=true)
![Transcript output page](screenshots/screen-09-transcript-output-page.png?raw=true)
![Video stream page](screenshots/screen-10-video-stream-page.png?raw=true)
![Thumbnail tool page](screenshots/screen-11-thumbnail-tool-page.png?raw=true)
![SEO optimizer page](screenshots/screen-12-seo-optimizer-page.png?raw=true)
![Channel audit page](screenshots/screen-13-channel-audit-page.png?raw=true)
![Idea generator page](screenshots/screen-14-idea-generator-page.png?raw=true)
