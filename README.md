# YouTube Tools Hub

YouTube Tools Hub is a Flask app that brings multiple creator utilities into one place. It now ships as a modern Material-style dashboard with six working tools and persistent run history.

## Current tools

- Transcript extractor (with quick text download)
- Thumbnail fetcher
- Video stream selector (quality-aware)
- Title and description SEO optimizer
- Channel audit (recent-video pattern analysis)
- Idea generator (hook, angle, and CTA suggestions)

## Why this version is production-ready

- Stateless server flow (no global in-memory stream cache)
- No server-side write to shared transcript files
- Better YouTube URL parsing (`watch`, `youtu.be`, `shorts`, `embed`, raw ID)
- Environment-driven security config (`SECRET_KEY`, optional `FORCE_HTTPS`)
- Persistent run history stored in SQL database
- Docker + Gunicorn runtime
- Modern Material-style dashboard UI

## Stack

- Flask 3.x
- Gunicorn
- Flask-SQLAlchemy
- pytube
- youtube-transcript-api
- Flask-Talisman

## Local development

1. Install dependencies

	`pip install -r requirements.txt`

2. Create `.env` (optional but recommended)

	```env
	SECRET_KEY=replace-with-random-secret
	FORCE_HTTPS=false
	DATABASE_URL=sqlite:///youtube_tools.db
	```

3. Run app

	`flask --app app run --debug`

4. Open browser

	`http://127.0.0.1:5000`

## Production run

Use Gunicorn (or equivalent process manager):

`gunicorn --bind 0.0.0.0:$PORT app:app`

Set environment variables in production:

- `SECRET_KEY` (required)
- `FORCE_HTTPS=true` when behind TLS/reverse proxy
- `DATABASE_URL` (defaults to local SQLite if omitted)

## Deploy to VM (Traefik + GitHub Actions)

This repo is configured to deploy the same way as your previous project:

- `docker-compose.prod.yml` with Traefik labels
- GitHub Actions workflow: `.github/workflows/deploy.yml`
- Production env template: `.env.production.example`

### 1) One-time VM setup

Install Docker + Docker Compose plugin on the VM, then create the shared Traefik network (same network your reverse proxy uses):

`docker network create web`

### 2) Create production env file on VM

On the VM deployment path, create `.env.production` from `.env.production.example` and set real values:

- `SECRET_KEY`
- `APP_DOMAIN` (e.g. `yttools.yourdomain.duckdns.org`)
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DATABASE_URL` (must match the DB credentials)

### 3) Configure GitHub repository secrets

- `VM_HOST` → VM public IP or DNS
- `SSH_PRIVATE_KEY` → private key content used for SSH login
- `VM_HOST_KEY` (optional but recommended) → host key from `ssh-keyscan`

### 4) Configure GitHub repository variables

- `VM_USER` → SSH user on VM
- `DEPLOY_PATH` → target folder on VM (example: `/opt/youtubetools`)
- `COMPOSE_FILE` (optional) → defaults to `${DEPLOY_PATH}/docker-compose.prod.yml`
- `ENV_FILE` (optional) → defaults to `${DEPLOY_PATH}/.env.production`

### 5) Trigger deployment

Push to `master` (or run workflow manually). The deploy job will:

- clone latest repo on VM
- build Docker image
- validate compose config
- start/update containers with `docker compose up -d`

### Notes

- This app uses PostgreSQL in production compose.
- `psycopg[binary]` is included in `requirements.txt` for `postgresql+psycopg://` support.
- If workflow says env file is missing, create `.env.production` at the path used by `ENV_FILE`.

## Operational endpoints

- `GET /health` — service liveness
- `GET /api/history` — latest tool run events as JSON
- `GET /history` — dashboard page for recent tool runs

## Suggested architecture for “all YouTube tools in one place”

Build the app as a hub with modular tool packages:

- `tools/transcript/`
- `tools/thumbnail/`
- `tools/download/`
- `tools/seo/`
- `tools/channel-audit/`
- `tools/idea-generator/`

Add shared infrastructure:

- PostgreSQL for saved jobs/history
- Redis + worker queue for long-running tasks
- Auth + per-user usage limits
- Structured logging + metrics + error tracking

## Priority roadmap

### P0 (foundation)

- Input validation and centralized error handling
- Auth and user workspace
- Persisted tool run history
- Background jobs for expensive tasks

### P1 (creator-focused tools)

- Title/description optimizer
- Transcript summarizer and chapter generator
- Keyword and hashtag helper
- Thumbnail A/B metadata tracker

### P2 (portfolio differentiation)

- Channel performance dashboard
- Export reports (PDF/CSV)
- Team/project workspace mode
- Public API for selected tools

## Compliance notes

- Follow YouTube Terms and API policies
- Avoid unauthorized redistribution/downloading workflows
- Clearly communicate usage limits and data handling in Privacy/Terms pages

## Screenshots

Home page  
![Home Page](screenshots/1.png?raw=true)

Enter Video Link  
![Enter Video Link](screenshots/2.png?raw=true)

Get Transcript  
![Get Transcript](screenshots/3.png?raw=true)

Download video  
![Download video](screenshots/4.png?raw=true)

Download thumbnail  
![Download thumbnail](screenshots/5.png?raw=true)
![Download thumbnail 2](screenshots/6.png?raw=true)
