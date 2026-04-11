# YouTube Tools Hub

YouTube Tools Hub is a Flask app that brings multiple creator utilities into one place. The current version focuses on transcript extraction, thumbnail access, and video stream selection, with a roadmap to evolve into a full portfolio of YouTube-focused tools.

## Current tools

- Transcript extractor (with quick text download)
- Thumbnail fetcher
- Video stream selector (quality-aware)

## Why this version is production-ready

- Stateless server flow (no global in-memory stream cache)
- No server-side write to shared transcript files
- Better YouTube URL parsing (`watch`, `youtu.be`, `shorts`, `embed`, raw ID)
- Environment-driven security config (`SECRET_KEY`, optional `FORCE_HTTPS`)
- Persistent run history stored in SQL database
- Docker + Gunicorn runtime

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

Use the Procfile command (or equivalent):

`gunicorn --bind 0.0.0.0:$PORT app:app`

Set environment variables in production:

- `SECRET_KEY` (required)
- `FORCE_HTTPS=true` when behind TLS/reverse proxy
- `DATABASE_URL` (defaults to local SQLite if omitted)

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
