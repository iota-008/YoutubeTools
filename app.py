import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi


db = SQLAlchemy()


def normalize_database_uri(database_uri):
    if database_uri.startswith('postgres://'):
        return database_uri.replace('postgres://', 'postgresql+psycopg://', 1)
    if database_uri.startswith('postgresql://'):
        return database_uri.replace('postgresql://', 'postgresql+psycopg://', 1)
    return database_uri


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')

default_db_path = os.path.join(app.root_path, 'youtube_tools.db')
database_uri = normalize_database_uri(os.environ.get('DATABASE_URL', f'sqlite:///{default_db_path}'))
app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

force_https = os.environ.get('FORCE_HTTPS', 'false').lower() == 'true'
Talisman(app, content_security_policy=None, force_https=force_https)


class ToolRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tool_name = db.Column(db.String(64), nullable=False, index=True)
    video_id = db.Column(db.String(16), nullable=True, index=True)
    video_url = db.Column(db.String(600), nullable=True)
    status = db.Column(db.String(16), nullable=False, default='ok')
    message = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


TOOL_CATALOG = [
    {
        'name': 'Transcript Extractor',
        'slug': 'transcript',
        'description': 'Extract and download text transcript from a YouTube video.',
        'status': 'live',
        'button_label': 'Get Transcript',
        'form_action': 'gettext',
    },
    {
        'name': 'Video Stream Selector',
        'slug': 'download',
        'description': 'Choose available progressive MP4 streams by quality.',
        'status': 'live',
        'button_label': 'Download Video',
        'form_action': 'download',
    },
    {
        'name': 'Thumbnail Tool',
        'slug': 'thumbnail',
        'description': 'Fetch and open the source thumbnail for any YouTube video.',
        'status': 'live',
        'button_label': 'Open Thumbnail',
        'form_action': 'thumbnail',
    },
    {
        'name': 'Title & Description Optimizer',
        'slug': 'seo-optimizer',
        'description': 'Generate improved title and description options for creators.',
        'status': 'planned',
        'button_label': 'Coming Soon',
    },
    {
        'name': 'Channel Audit',
        'slug': 'channel-audit',
        'description': 'Analyze upload patterns and high-performing content themes.',
        'status': 'planned',
        'button_label': 'Coming Soon',
    },
    {
        'name': 'Idea Generator',
        'slug': 'idea-generator',
        'description': 'Generate video ideas using topic, niche, and trend inputs.',
        'status': 'planned',
        'button_label': 'Coming Soon',
    },
]


def extract_video_id(raw_url):
    candidate = (raw_url or '').strip()
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.hostname in {'youtu.be', 'www.youtu.be'}:
        return parsed.path.lstrip('/')[:11]

    if parsed.hostname and 'youtube.com' in parsed.hostname:
        query_video_id = parse_qs(parsed.query).get('v', [''])[0]
        if query_video_id:
            return query_video_id[:11]

        path_parts = [part for part in parsed.path.split('/') if part]
        if len(path_parts) >= 2 and path_parts[0] in {'embed', 'shorts', 'live'}:
            return path_parts[1][:11]

    if len(candidate) == 11 and all(char.isalnum() or char in {'-', '_'} for char in candidate):
        return candidate

    return None


def save_tool_run(tool_name, status, message=None, video_url=None, video_id=None):
    db.session.add(
        ToolRun(
            tool_name=tool_name,
            status=status,
            message=message,
            video_url=video_url,
            video_id=video_id,
        )
    )
    db.session.commit()


def get_recent_runs(limit=10):
    return ToolRun.query.order_by(ToolRun.created_at.desc()).limit(limit).all()

@app.route('/')
def index():
    return render_template('index.html', tools=TOOL_CATALOG, recent_runs=get_recent_runs())


app.errorhandler(404)
def page_not_found(e):
    return render_template('page_not_found.html'), 404


@app.route('/history')
def history():
    records = ToolRun.query.order_by(ToolRun.created_at.desc()).limit(100).all()
    return render_template('history.html', records=records)


@app.route('/api/history')
def api_history():
    records = ToolRun.query.order_by(ToolRun.created_at.desc()).limit(50).all()
    payload = [
        {
            'id': row.id,
            'tool_name': row.tool_name,
            'video_id': row.video_id,
            'video_url': row.video_url,
            'status': row.status,
            'message': row.message,
            'created_at': row.created_at.isoformat() if row.created_at else None,
        }
        for row in records
    ]
    return jsonify({'count': len(payload), 'runs': payload})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/gettext', methods=["GET", "POST"])
def gettext():
    if request.method != 'POST':
        flash('Use the home page to submit a YouTube URL.')
        return redirect(url_for('index'), code=302)

    raw_url = request.form.get('url', '').strip()
    video_id = extract_video_id(raw_url)
    if not video_id:
        save_tool_run('transcript', 'error', 'Invalid YouTube URL', raw_url)
        flash('Enter a valid YouTube URL.')
        return redirect(url_for('index'), code=302)

    try:
        transcript_items = YouTubeTranscriptApi.get_transcript(video_id)
    except Exception:
        save_tool_run('transcript', 'error', 'Transcript unavailable', raw_url, video_id)
        flash('Transcript not available for this video.')
        return redirect(url_for('index'), code=302)

    transcript_text = '\n'.join(item.get('text', '').strip() for item in transcript_items if item.get('text'))
    save_tool_run('transcript', 'ok', 'Transcript extracted', raw_url, video_id)
    return render_template('transcript.html', transcript_text=transcript_text)


@app.route('/download', methods=["GET", "POST"])
def download():
    if request.method != 'POST':
        flash('Use the home page to submit a YouTube URL.')
        return redirect(url_for('index'), code=302)

    raw_url = request.form.get('url', '').strip()
    video_id = extract_video_id(raw_url)
    if not video_id:
        save_tool_run('video_download', 'error', 'Invalid YouTube URL', raw_url)
        flash('Enter a valid YouTube URL.')
        return redirect(url_for('index'), code=302)

    try:
        yt = YouTube(raw_url)
        streams = list(
            yt.streams
            .filter(progressive=True, file_extension='mp4')
            .order_by('resolution')
            .desc()
        )
    except Exception:
        save_tool_run('video_download', 'error', 'Unable to fetch stream options', raw_url, video_id)
        flash('Could not fetch download options for this video.')
        return redirect(url_for('index'), code=302)

    if not streams:
        save_tool_run('video_download', 'error', 'No progressive streams', raw_url, video_id)
        flash('No progressive MP4 streams available for this video.')
        return redirect(url_for('index'), code=302)

    stream_options = []
    for stream in streams:
        size_mb = None
        if stream.filesize:
            size_mb = round(stream.filesize / (1024 * 1024), 2)
        stream_options.append(
            {
                'itag': str(stream.itag),
                'resolution': stream.resolution or 'unknown',
                'mime_type': stream.mime_type or 'video/mp4',
                'fps': stream.fps,
                'size_mb': size_mb,
            }
        )

    save_tool_run('video_download', 'ok', f'Stream options fetched ({len(stream_options)})', raw_url, video_id)
    return render_template('download.html', stream_options=stream_options, url=raw_url)


@app.route('/video-quality', methods=["POST"])
def video_quality():
    raw_url = request.form.get('url', '').strip()
    itag = request.form.get('itag', '').strip()
    video_id = extract_video_id(raw_url)

    if not raw_url or not itag.isdigit():
        save_tool_run('video_download', 'error', 'Invalid stream selection', raw_url, video_id)
        flash('Invalid download selection.')
        return redirect(url_for('index'), code=302)

    try:
        yt = YouTube(raw_url)
        stream = yt.streams.get_by_itag(int(itag))
        if not stream:
            save_tool_run('video_download', 'error', 'Selected stream unavailable', raw_url, video_id)
            flash('Selected stream is not available anymore.')
            return redirect(url_for('index'), code=302)
        save_tool_run('video_download', 'ok', f'Redirected stream itag={itag}', raw_url, video_id)
        return redirect(stream.url, code=302)
    except Exception:
        save_tool_run('video_download', 'error', 'Failed to prepare stream URL', raw_url, video_id)
        flash('Failed to prepare video download link.')
        return redirect(url_for('index'), code=302)


@app.route('/thumbnail', methods=["POST", "GET"])
def thumbnail():
    if request.method != 'POST':
        flash('Use the home page to submit a YouTube URL.')
        return redirect(url_for('index'), code=302)

    raw_url = request.form.get('url', '').strip()
    video_id = extract_video_id(raw_url)
    if not video_id:
        save_tool_run('thumbnail', 'error', 'Invalid YouTube URL', raw_url)
        flash('Enter a valid YouTube URL.')
        return redirect(url_for('index'), code=302)

    try:
        video = YouTube(raw_url)
        thumbnail_url = video.thumbnail_url
    except Exception:
        save_tool_run('thumbnail', 'error', 'Failed to fetch thumbnail', raw_url, video_id)
        flash('Could not fetch thumbnail for this video.')
        return redirect(url_for('index'), code=302)

    save_tool_run('thumbnail', 'ok', 'Thumbnail fetched', raw_url, video_id)
    return render_template('thumbnail.html', url=thumbnail_url)

@app.route('/robots.txt')
@app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


with app.app_context():
    db.create_all()
