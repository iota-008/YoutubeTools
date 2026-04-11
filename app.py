import os
import re
from io import BytesIO
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from collections import Counter
from urllib.parse import parse_qs, urlparse

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None

try:
    from pytubefix import Channel as YouTubeChannel
    from pytubefix import YouTube as YouTubeVideo
except ImportError:
    from pytube import Channel as YouTubeChannel
    from pytube import YouTube as YouTubeVideo

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
        'path': '/tools/transcript',
    },
    {
        'name': 'Video Stream Selector',
        'slug': 'download',
        'description': 'Choose available progressive MP4 streams by quality.',
        'status': 'live',
        'button_label': 'Download Video',
        'path': '/tools/download',
    },
    {
        'name': 'Thumbnail Tool',
        'slug': 'thumbnail',
        'description': 'Fetch and open the source thumbnail for any YouTube video.',
        'status': 'live',
        'button_label': 'Get Thumbnail',
        'path': '/tools/thumbnail',
    },
    {
        'name': 'Title & Description Optimizer',
        'slug': 'seo-optimizer',
        'description': 'Generate improved title and description options for creators.',
        'status': 'live',
        'button_label': 'Optimize SEO',
        'path': '/tools/seo-optimizer',
    },
    {
        'name': 'Channel Audit',
        'slug': 'channel-audit',
        'description': 'Analyze upload patterns and high-performing content themes.',
        'status': 'live',
        'button_label': 'Run Audit',
        'path': '/tools/channel-audit',
    },
    {
        'name': 'Idea Generator',
        'slug': 'idea-generator',
        'description': 'Generate video ideas using topic, niche, and trend inputs.',
        'status': 'live',
        'button_label': 'Generate Ideas',
        'path': '/tools/idea-generator',
    },
]

TRANSCRIPT_LANGUAGE_OPTIONS = [
    ('en', 'English'),
    ('hi', 'Hindi'),
    ('es', 'Spanish'),
    ('fr', 'French'),
    ('de', 'German'),
    ('pt', 'Portuguese'),
    ('ar', 'Arabic'),
    ('ja', 'Japanese'),
    ('ko', 'Korean'),
    ('zh-Hans', 'Chinese (Simplified)'),
]

STOP_WORDS = {
    'the', 'and', 'for', 'that', 'with', 'this', 'from', 'your', 'you', 'are', 'how', 'what',
    'why', 'when', 'where', 'into', 'without', 'using', 'about', 'after', 'before', 'have',
    'has', 'had', 'was', 'were', 'can', 'will', 'its', 'our', 'their', 'they', 'them', 'a',
    'an', 'to', 'in', 'on', 'of', 'at', 'it', 'is', 'be', 'as', 'or', 'by', 'we', 'i', 'my',
}

YT_HTTP_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/123.0.0.0 Safari/537.36'
    )
}


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


def build_video_url_candidates(raw_url, video_id):
    candidates = []
    if video_id:
        candidates.append(f'https://www.youtube.com/watch?v={video_id}')
        candidates.append(f'https://youtu.be/{video_id}')
        candidates.append(f'https://m.youtube.com/watch?v={video_id}')

    if raw_url and raw_url not in candidates:
        candidates.append(raw_url)

    unique_candidates = []
    for candidate in candidates:
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates


def get_youtube_video(raw_url, video_id):
    last_error = None
    for candidate_url in build_video_url_candidates(raw_url, video_id):
        try:
            return YouTubeVideo(candidate_url)
        except Exception as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    raise ValueError('Unable to resolve a valid YouTube video URL.')


def tokenize_words(text):
    words = re.findall(r"[A-Za-z0-9']+", (text or '').lower())
    return [word for word in words if len(word) > 2 and word not in STOP_WORDS]


def top_keywords_from_texts(texts, limit=6):
    counter = Counter()
    for text in texts:
        counter.update(tokenize_words(text))
    return [word for word, _ in counter.most_common(limit)]


def build_seo_suggestions(title, keywords, audience, tone):
    clean_title = (title or 'Your next video').strip()
    keyword_block = ', '.join(keywords[:3]) if keywords else 'step-by-step strategy'
    audience_block = audience or 'creators'
    tone_block = tone or 'clear'

    title_suggestions = [
        f"{clean_title}: {keyword_block} for {audience_block}",
        f"{keyword_block.title()} Blueprint ({audience_block})",
        f"{clean_title} — {tone_block.title()} Guide",
        f"{clean_title}: What Actually Works in 2026",
    ]

    description_suggestions = [
        (
            f"In this video, we break down {keyword_block} for {audience_block}. "
            f"You will get practical steps, common mistakes to avoid, and an actionable workflow to apply today."
        ),
        (
            f"Want better results with {keyword_block}? This {tone_block} tutorial covers strategy, execution, "
            f"and optimization so {audience_block} can grow faster."
        ),
    ]

    hashtag_base = keywords[:3] if keywords else ['youtube', 'content', 'creator']
    hashtags = [f"#{re.sub(r'[^a-zA-Z0-9]', '', tag)}" for tag in hashtag_base if tag]

    return title_suggestions, description_suggestions, hashtags


def normalize_channel_input(raw_input):
    candidate = (raw_input or '').strip()
    if not candidate:
        return None
    if candidate.startswith('http://') or candidate.startswith('https://'):
        return candidate
    return f'https://www.youtube.com/{candidate.lstrip('/')}'


def extract_channel_id_from_url_or_page(channel_url):
    parsed = urlparse(channel_url)
    path_parts = [part for part in parsed.path.split('/') if part]
    if len(path_parts) >= 2 and path_parts[0] == 'channel' and path_parts[1].startswith('UC'):
        return path_parts[1]

    response = requests.get(channel_url, timeout=10, headers=YT_HTTP_HEADERS)
    if not response.ok:
        return None

    match = re.search(r'"channelId":"(UC[0-9A-Za-z_-]{22})"', response.text)
    if match:
        return match.group(1)

    alt_match = re.search(r'\/channel\/(UC[0-9A-Za-z_-]{22})', response.text)
    if alt_match:
        return alt_match.group(1)

    return None


def fetch_channel_feed_entries(channel_url, limit=8):
    channel_id = extract_channel_id_from_url_or_page(channel_url)
    if not channel_id:
        return []

    feed_url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    feed_response = requests.get(feed_url, timeout=10, headers=YT_HTTP_HEADERS)
    if not feed_response.ok:
        return []

    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'yt': 'http://www.youtube.com/xml/schemas/2015',
    }

    root = ET.fromstring(feed_response.text)
    entries = []
    for entry in root.findall('atom:entry', ns)[:limit]:
        title = entry.findtext('atom:title', default='', namespaces=ns)
        video_id = entry.findtext('yt:videoId', default='', namespaces=ns)
        link_node = entry.find('atom:link', ns)
        url = link_node.get('href') if link_node is not None else ''
        if not url and video_id:
            url = f'https://www.youtube.com/watch?v={video_id}'

        if url:
            entries.append({'url': url, 'title': title, 'video_id': video_id})

    return entries


def fetch_channel_video_candidates(channel_url, limit=8):
    try:
        channel = Channel(channel_url)
        urls = list(channel.video_urls)[:limit]
        if urls:
            return [{'url': url, 'title': '', 'video_id': extract_video_id(url)} for url in urls], 'pytube'
    except Exception:
        pass

    feed_entries = fetch_channel_feed_entries(channel_url, limit=limit)
    if feed_entries:
        return feed_entries, 'feed'

    raise ValueError('No videos found for this channel.')


def run_channel_audit(channel_url):
    candidates, data_source = fetch_channel_video_candidates(channel_url, limit=8)
    if not candidates:
        raise ValueError('No videos found for this channel.')

    title_lengths = []
    durations = []
    views = []
    titles = []
    sampled_videos = []
    enriched_count = 0

    for item in candidates:
        video_url = item['url']
        title = item.get('title') or ''
        candidate_video_id = item.get('video_id') or extract_video_id(video_url)
        duration_seconds = None
        video_views = None

        try:
            yt = get_youtube_video(video_url, candidate_video_id)
            title = yt.title or title
            duration_seconds = int(yt.length) if yt.length else None
            video_views = int(yt.views) if yt.views else None
            enriched_count += 1
        except Exception:
            pass

        title = title or 'Untitled video'
        titles.append(title)
        title_lengths.append(len(title))
        if duration_seconds is not None:
            durations.append(duration_seconds)
        if video_views is not None:
            views.append(video_views)

        sampled_videos.append(
            {
                'title': title,
                'url': video_url,
                'duration_min': round(duration_seconds / 60, 1) if duration_seconds is not None else None,
                'views': video_views,
            }
        )

    avg_title_len = round(sum(title_lengths) / len(title_lengths), 1)
    avg_duration_min = round((sum(durations) / len(durations)) / 60, 1) if durations else None
    avg_views = int(sum(views) / len(views)) if views else None
    top_keywords = top_keywords_from_texts(titles, limit=8)

    recommendations = []
    if avg_title_len < 45:
        recommendations.append('Increase title specificity; many titles are short and may miss search context.')
    if avg_title_len > 70:
        recommendations.append('Trim title length; target 45-65 characters for mobile readability.')
    if avg_duration_min is not None and avg_duration_min < 6:
        recommendations.append('Consider longer value-dense formats to improve session watch time.')
    if avg_duration_min is not None and avg_duration_min > 18:
        recommendations.append('Test tighter edits and chaptering for retention on long-form videos.')
    if avg_duration_min is None:
        recommendations.append('Duration metrics unavailable for some videos; audit used fallback metadata.')
    if avg_views is None:
        recommendations.append('View metrics unavailable for some videos; run audit again later for full enrichment.')
    if not recommendations:
        recommendations.append('Current title length and duration ranges look healthy; focus on packaging consistency.')

    return {
        'channel_url': channel_url,
        'sample_size': len(sampled_videos),
        'data_source': data_source,
        'enriched_count': enriched_count,
        'avg_title_length': avg_title_len,
        'avg_duration_min': avg_duration_min,
        'avg_views': avg_views,
        'top_keywords': top_keywords,
        'recommendations': recommendations,
        'sampled_videos': sampled_videos,
    }


def generate_idea_pack(niche, audience, content_goal, count):
    formats = ['Tutorial', 'Case Study', 'Breakdown', 'Checklist', 'Q&A', 'Myth Busting']
    hooks = [
        'What nobody tells you about',
        'I tested this for 30 days:',
        'Do this before you start',
        'The fastest way to improve',
        'Common mistakes in',
    ]
    ctas = [
        'Comment your biggest challenge for a follow-up video.',
        'Save this workflow and apply it this week.',
        'Share this with a creator who needs this.',
    ]

    ideas = []
    safe_count = max(3, min(count, 20))
    niche_title = niche.strip().title() if niche else 'Your Niche'
    audience_title = audience.strip().title() if audience else 'Creators'
    goal_text = content_goal.strip().lower() if content_goal else 'growth'

    for index in range(safe_count):
        format_choice = formats[index % len(formats)]
        hook_choice = hooks[index % len(hooks)]
        cta_choice = ctas[index % len(ctas)]
        title = f"{format_choice}: {hook_choice} {niche_title} ({audience_title})"
        angle = f"Focus on {goal_text} with practical steps and a before/after result narrative."
        ideas.append({'title': title, 'angle': angle, 'cta': cta_choice})

    return ideas


def fetch_video_metadata(raw_url, video_id):
    metadata = {
        'title': f'YouTube Video {video_id}',
        'description': '',
        'warning': None,
    }

    try:
        yt = get_youtube_video(raw_url, video_id)
        metadata['title'] = yt.title or metadata['title']
        metadata['description'] = (yt.description or '')[:4000]
        return metadata
    except Exception:
        pass

    try:
        response = requests.get(
            'https://www.youtube.com/oembed',
            params={'url': raw_url, 'format': 'json'},
            timeout=8,
        )
        if response.ok:
            payload = response.json()
            metadata['title'] = payload.get('title') or metadata['title']
            metadata['warning'] = 'Limited metadata available; using fallback source.'
            return metadata
    except Exception:
        pass

    metadata['warning'] = 'Limited metadata available; generated SEO suggestions from URL context only.'
    return metadata


def build_preferred_transcript_languages(selected_language):
    fallback_languages = ['en', 'en-US', 'en-GB']
    supported_languages = {code for code, _ in TRANSCRIPT_LANGUAGE_OPTIONS}
    language = (selected_language or 'en').strip()

    if not language or language not in supported_languages:
        language = 'en'

    preferred_languages = []
    normalized = language.lower()

    preferred_languages.append(language)
    if '-' in language:
        preferred_languages.append(language.split('-', 1)[0])

    if normalized.startswith('en'):
        preferred_languages.extend(['en', 'en-US', 'en-GB'])
    else:
        preferred_languages.extend(fallback_languages)

    deduped = []
    seen = set()
    for item in preferred_languages:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    return deduped, language


def fetch_transcript_items(video_id, selected_language='en'):
    preferred_languages, target_language = build_preferred_transcript_languages(selected_language)
    target_prefix = target_language.split('-', 1)[0].lower()
    warning_message = None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        try:
            preferred = transcript_list.find_transcript(preferred_languages)
            items = preferred.fetch()
            if items:
                preferred_language_code = (preferred.language_code or '').lower()
                if target_prefix != 'en' and not preferred_language_code.startswith(target_prefix):
                    warning_message = 'Selected language not available for this video. Showing default English transcript.'
                return items, warning_message
        except Exception:
            pass

        priority_scores = {code.lower(): 100 - idx for idx, code in enumerate(preferred_languages)}

        candidates = []
        for transcript in transcript_list:
            score = 0
            language_code = (transcript.language_code or '').lower()
            if language_code in priority_scores:
                score += priority_scores[language_code]
            elif language_code.startswith(target_prefix):
                score += 70
            elif language_code.startswith('en'):
                score += 40
            if not transcript.is_generated:
                score += 10
            if transcript.is_translatable:
                score += 5
            candidates.append((score, transcript))

        candidates.sort(key=lambda entry: entry[0], reverse=True)
        for _, transcript in candidates:
            try:
                active = transcript
                language_code = (active.language_code or '').lower()

                if language_code.startswith(target_prefix):
                    items = active.fetch()
                    if items:
                        if transcript.is_generated:
                            return items, 'Using auto-generated captions for this video.'
                        return items, warning_message
                    continue

                if active.is_translatable:
                    try:
                        active = active.translate(target_language)
                    except Exception:
                        if target_prefix != 'en':
                            active = active.translate('en')
                            warning_message = 'Selected language not available. Showing default English transcript.'
                        else:
                            continue

                items = active.fetch()
                if items:
                    warning = warning_message
                    if transcript.is_generated:
                        warning = 'Using auto-generated captions for this video.'
                    return items, warning
            except Exception:
                continue
    except Exception:
        pass

    ytdlp_items = fetch_transcript_via_ytdlp(video_id, preferred_languages=preferred_languages)
    if ytdlp_items:
        return ytdlp_items, 'Using fallback captions source for this video.'

    return None, 'Transcript unavailable. This video may not have accessible captions.'


def parse_vtt_caption_text(raw_text):
    lines = []
    for line in raw_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.startswith('WEBVTT'):
            continue
        if '-->' in candidate:
            continue
        if candidate.isdigit():
            continue
        if candidate.startswith('NOTE'):
            continue
        lines.append(candidate)

    cleaned = []
    for line in lines:
        text = re.sub(r'<[^>]+>', '', line).strip()
        if text and (not cleaned or cleaned[-1] != text):
            cleaned.append(text)

    return [{'text': item} for item in cleaned]


def parse_json3_caption_text(payload):
    items = []
    try:
        events = payload.get('events', [])
        for event in events:
            segments = event.get('segs', [])
            text = ''.join(segment.get('utf8', '') for segment in segments).strip()
            text = text.replace('\n', ' ').strip()
            if text:
                items.append({'text': text})
    except Exception:
        return []
    return items


def parse_xml_caption_text(raw_text):
    try:
        root = ET.fromstring(raw_text)
    except Exception:
        return []

    items = []
    for node in root.iter():
        text = (node.text or '').strip()
        if text:
            items.append({'text': text})
    return items


def fetch_transcript_via_ytdlp(video_id, preferred_languages=None):
    if YoutubeDL is None:
        return None

    video_url = f'https://www.youtube.com/watch?v={video_id}'
    options = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception:
        return None

    tracks_by_lang = []
    for source in (info.get('subtitles') or {}, info.get('automatic_captions') or {}):
        for language, tracks in source.items():
            tracks_by_lang.append((language, tracks or []))

    if not tracks_by_lang:
        return None

    preferred = preferred_languages or ['en', 'en-US', 'en-GB']
    preferred_lower = [code.lower() for code in preferred]
    preferred_primary = [code.split('-', 1)[0].lower() for code in preferred_lower]

    def matches_preferred(lang):
        lower_lang = (lang or '').lower()
        if lower_lang in preferred_lower:
            return True
        for prefix in preferred_primary:
            if lower_lang == prefix:
                return True
            if lower_lang.startswith(prefix + '-'):
                return True
            if lower_lang.startswith(prefix + '_'):
                return True
            if lower_lang.startswith(prefix + '.'):
                return True
            if lower_lang.endswith('.' + prefix):
                return True
        return False

    def lang_score(lang):
        lower_lang = (lang or '').lower()
        if lower_lang in preferred_lower:
            return 100
        if any(lower_lang.startswith(prefix) for prefix in preferred_primary):
            return 85
        if lower_lang.startswith('en'):
            return 75
        return 10

    tracks_by_lang.sort(key=lambda item: lang_score(item[0]), reverse=True)

    for language, tracks in tracks_by_lang:
        if not matches_preferred(language):
            continue
        if not tracks:
            continue
        sorted_tracks = sorted(
            tracks,
            key=lambda track: 0 if track.get('ext') == 'vtt' else 1,
        )
        for track in sorted_tracks:
            track_url = track.get('url')
            ext = (track.get('ext') or '').lower()
            if not track_url:
                continue
            try:
                response = requests.get(track_url, timeout=10, headers=YT_HTTP_HEADERS)
                if response.status_code >= 400:
                    continue
                if ext == 'json3':
                    items = parse_json3_caption_text(response.json())
                elif ext in {'vtt', 'srv3'}:
                    items = parse_vtt_caption_text(response.text)
                else:
                    items = parse_xml_caption_text(response.text)
                if items:
                    return items
            except Exception:
                continue

    return None


def fetch_stream_options_via_ytdlp(raw_url):
    if YoutubeDL is None:
        return []

    options = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(raw_url, download=False)
    except Exception:
        return []

    formats = info.get('formats') or []
    stream_options = []
    for fmt in formats:
        if fmt.get('vcodec') in {None, 'none'}:
            continue
        if fmt.get('acodec') in {None, 'none'}:
            continue
        ext = (fmt.get('ext') or '').lower()
        if ext != 'mp4':
            continue

        direct_url = fmt.get('url')
        if not direct_url:
            continue

        filesize = fmt.get('filesize') or fmt.get('filesize_approx')
        size_mb = round(filesize / (1024 * 1024), 2) if filesize else None
        resolution = f"{fmt.get('height')}p" if fmt.get('height') else (fmt.get('format_note') or 'unknown')

        stream_options.append(
            {
                'itag': str(fmt.get('format_id') or ''),
                'resolution': resolution,
                'mime_type': f"video/{ext}",
                'fps': fmt.get('fps'),
                'size_mb': size_mb,
                'source': 'ytdlp',
                'direct_url': direct_url,
            }
        )

    stream_options.sort(
        key=lambda item: (
            int(re.sub(r'[^0-9]', '', item['resolution']) or 0),
            float(item['fps'] or 0),
        ),
        reverse=True,
    )
    return stream_options


def resolve_thumbnail_url(raw_url, video_id):
    try:
        video = get_youtube_video(raw_url, video_id)
        if video.thumbnail_url:
            return video.thumbnail_url, None
    except Exception:
        pass

    candidates = [
        f'https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg',
        f'https://i.ytimg.com/vi/{video_id}/sddefault.jpg',
        f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
    ]

    for candidate in candidates:
        try:
            response = requests.head(candidate, timeout=6, allow_redirects=True, headers=YT_HTTP_HEADERS)
            if response.status_code < 400:
                return candidate, 'Thumbnail fetched using fallback URL.'
        except Exception:
            continue

    return f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg', 'Using default thumbnail fallback URL.'


def get_thumbnail_options(video_id):
    options = [
        {'quality': 'maxres', 'label': 'Max Resolution', 'url': f'https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg'},
        {'quality': 'sd', 'label': 'Standard Resolution', 'url': f'https://i.ytimg.com/vi/{video_id}/sddefault.jpg'},
        {'quality': 'hq', 'label': 'High Resolution', 'url': f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'},
    ]

    for option in options:
        option['available'] = False
        try:
            response = requests.head(option['url'], timeout=6, allow_redirects=True, headers=YT_HTTP_HEADERS)
            if response.status_code < 400:
                option['available'] = True
        except Exception:
            option['available'] = False

    if not any(item['available'] for item in options):
        options[-1]['available'] = True

    return options

@app.route('/')
def index():
    return render_template('index.html', tools=TOOL_CATALOG, recent_runs=get_recent_runs())


@app.errorhandler(404)
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


@app.route('/tools/transcript')
def transcript_tool():
    return render_template(
        'video_input_tool.html',
        tool_title='Transcript Extractor',
        tool_subtitle='Paste a YouTube URL, choose transcript language, and fallback to English if unavailable.',
        field_label='YouTube URL',
        submit_label='Get Transcript',
        submit_action=url_for('gettext'),
        language_options=TRANSCRIPT_LANGUAGE_OPTIONS,
        selected_language='en',
    )


@app.route('/tools/download')
def download_tool():
    return render_template(
        'video_input_tool.html',
        tool_title='Video Stream Selector',
        tool_subtitle='Paste a YouTube URL to load available video quality options.',
        field_label='YouTube URL',
        submit_label='Load Stream Options',
        submit_action=url_for('download'),
    )


@app.route('/tools/thumbnail')
def thumbnail_tool():
    return render_template(
        'video_input_tool.html',
        tool_title='Thumbnail Tool',
        tool_subtitle='Paste a YouTube URL to fetch and download thumbnail resolutions.',
        field_label='YouTube URL',
        submit_label='Fetch Thumbnail',
        submit_action=url_for('thumbnail'),
    )


@app.route('/tools/seo-optimizer', methods=['GET', 'POST'])
def seo_optimizer():
    if request.method != 'POST':
        return render_template('seo_optimizer.html', result=None)

    raw_url = request.form.get('url', '').strip()
    audience = request.form.get('audience', '').strip()
    tone = request.form.get('tone', '').strip()
    video_id = extract_video_id(raw_url)
    if not video_id:
        save_tool_run('seo_optimizer', 'error', 'Invalid YouTube URL', raw_url)
        flash('Enter a valid YouTube URL for SEO optimization.')
        return redirect(url_for('seo_optimizer'), code=302)

    metadata = fetch_video_metadata(raw_url, video_id)
    title = metadata['title']
    description = metadata['description']

    transcript_items, _ = fetch_transcript_items(video_id)
    transcript_items = transcript_items or []

    transcript_text = ' '.join(item.get('text', '') for item in transcript_items)
    keywords = top_keywords_from_texts([title, description, transcript_text], limit=8)
    title_suggestions, description_suggestions, hashtags = build_seo_suggestions(
        title=title,
        keywords=keywords,
        audience=audience,
        tone=tone,
    )

    result = {
        'source_title': title,
        'keywords': keywords,
        'title_suggestions': title_suggestions,
        'description_suggestions': description_suggestions,
        'hashtags': hashtags,
        'video_url': raw_url,
        'warning': metadata['warning'],
    }
    save_tool_run('seo_optimizer', 'ok', 'Generated SEO suggestions', raw_url, video_id)
    return render_template('seo_optimizer.html', result=result)


@app.route('/tools/channel-audit', methods=['GET', 'POST'])
def channel_audit():
    if request.method != 'POST':
        return render_template('channel_audit.html', report=None)

    raw_channel = request.form.get('channel_url', '').strip()
    channel_url = normalize_channel_input(raw_channel)
    if not channel_url:
        save_tool_run('channel_audit', 'error', 'Invalid channel input', raw_channel)
        flash('Enter a valid channel URL or handle path.')
        return redirect(url_for('channel_audit'), code=302)

    try:
        report = run_channel_audit(channel_url)
        save_tool_run('channel_audit', 'ok', 'Channel audit completed', channel_url)
        return render_template('channel_audit.html', report=report)
    except Exception:
        save_tool_run('channel_audit', 'error', 'Failed to audit channel', channel_url)
        flash('Unable to audit this channel right now. Try a channel URL with public videos.')
        return redirect(url_for('channel_audit'), code=302)


@app.route('/tools/idea-generator', methods=['GET', 'POST'])
def idea_generator():
    if request.method != 'POST':
        return render_template('idea_generator.html', ideas=None)

    niche = request.form.get('niche', '').strip()
    audience = request.form.get('audience', '').strip()
    content_goal = request.form.get('content_goal', '').strip()
    count_raw = request.form.get('count', '10').strip()

    try:
        count = int(count_raw)
    except ValueError:
        count = 10

    ideas = generate_idea_pack(niche=niche, audience=audience, content_goal=content_goal, count=count)
    save_tool_run('idea_generator', 'ok', f'Generated {len(ideas)} ideas')
    return render_template(
        'idea_generator.html',
        ideas=ideas,
        niche=niche,
        audience=audience,
        content_goal=content_goal,
    )


@app.route('/gettext', methods=["GET", "POST"])
def gettext():
    if request.method != 'POST':
        flash('Use the home page to submit a YouTube URL.')
        return redirect(url_for('index'), code=302)

    raw_url = request.form.get('url', '').strip()
    selected_language = request.form.get('language', 'en').strip() or 'en'
    video_id = extract_video_id(raw_url)
    if not video_id:
        save_tool_run('transcript', 'error', 'Invalid YouTube URL', raw_url)
        flash('Enter a valid YouTube URL.')
        return redirect(url_for('index'), code=302)

    transcript_items, warning = fetch_transcript_items(video_id, selected_language=selected_language)
    if not transcript_items:
        save_tool_run('transcript', 'error', 'Transcript unavailable', raw_url, video_id)
        flash(warning or 'Transcript not available for this video.')
        return redirect(url_for('index'), code=302)

    transcript_text = '\n'.join(item.get('text', '').strip() for item in transcript_items if item.get('text'))
    save_tool_run('transcript', 'ok', 'Transcript extracted', raw_url, video_id)
    if warning:
        flash(warning)
    return render_template('transcript.html', transcript_text=transcript_text, selected_language=selected_language)


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

    stream_options = []
    try:
        yt = get_youtube_video(raw_url, video_id)
        streams = list(
            yt.streams
            .filter(progressive=True, file_extension='mp4')
            .order_by('resolution')
            .desc()
        )
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
                    'source': 'pytube',
                    'direct_url': '',
                }
            )
    except Exception:
        stream_options = []

    if not stream_options:
        stream_options = fetch_stream_options_via_ytdlp(raw_url)

    if not stream_options:
        save_tool_run('video_download', 'error', 'Unable to fetch stream options', raw_url, video_id)
        flash('Could not fetch download options for this video.')
        return redirect(url_for('index'), code=302)

    save_tool_run('video_download', 'ok', f'Stream options fetched ({len(stream_options)})', raw_url, video_id)
    return render_template('download.html', stream_options=stream_options, url=raw_url)


@app.route('/video-quality', methods=["POST"])
def video_quality():
    raw_url = request.form.get('url', '').strip()
    itag = request.form.get('itag', '').strip()
    source = (request.form.get('source') or 'pytube').strip().lower()
    direct_url = (request.form.get('direct_url') or '').strip()
    video_id = extract_video_id(raw_url)

    if not raw_url or not itag.isdigit():
        save_tool_run('video_download', 'error', 'Invalid stream selection', raw_url, video_id)
        flash('Invalid download selection.')
        return redirect(url_for('index'), code=302)

    if source == 'ytdlp':
        if direct_url.startswith('http://') or direct_url.startswith('https://'):
            save_tool_run('video_download', 'ok', f'Fallback redirect stream format={itag}', raw_url, video_id)
            return redirect(direct_url, code=302)
        save_tool_run('video_download', 'error', 'Missing fallback stream URL', raw_url, video_id)
        flash('Selected stream URL expired. Refresh options and try again.')
        return redirect(url_for('download_tool'), code=302)

    try:
        yt = get_youtube_video(raw_url, video_id)
        stream = yt.streams.get_by_itag(int(itag))
        if not stream:
            save_tool_run('video_download', 'error', 'Selected stream unavailable', raw_url, video_id)
            flash('Selected stream is not available anymore.')
            return redirect(url_for('index'), code=302)

        safe_title = re.sub(r'[^A-Za-z0-9._-]+', '_', (yt.title or video_id or 'youtube_video')).strip('_')
        safe_title = (safe_title or 'youtube_video')[:90]
        extension = 'mp4'
        if stream.mime_type and '/' in stream.mime_type:
            extension = stream.mime_type.split('/', 1)[1]
        file_name = f"{safe_title}-{stream.resolution or 'video'}-{itag}.{extension}"

        try:
            buffer = BytesIO()
            stream.stream_to_buffer(buffer)
            buffer.seek(0)
            save_tool_run('video_download', 'ok', f'Downloaded stream itag={itag}', raw_url, video_id)
            return send_file(
                buffer,
                mimetype=stream.mime_type or 'video/mp4',
                as_attachment=True,
                download_name=file_name,
            )
        except Exception:
            if getattr(stream, 'url', None):
                save_tool_run('video_download', 'ok', f'Fallback redirect stream itag={itag}', raw_url, video_id)
                flash('Using fallback stream URL for this video quality.')
                return redirect(stream.url, code=302)

            save_tool_run('video_download', 'error', 'Failed to stream selected quality', raw_url, video_id)
            flash('Unable to download this stream right now. Try another quality.')
            return redirect(url_for('index'), code=302)
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

    thumbnail_url, warning = resolve_thumbnail_url(raw_url, video_id)
    thumbnail_options = get_thumbnail_options(video_id)

    save_tool_run('thumbnail', 'ok', 'Thumbnail fetched', raw_url, video_id)
    if warning:
        flash(warning)
    return render_template(
        'thumbnail.html',
        url=thumbnail_url,
        video_id=video_id,
        thumbnail_options=thumbnail_options,
    )


@app.route('/download-thumbnail')
def download_thumbnail():
    video_id = (request.args.get('video_id') or '').strip()
    quality = (request.args.get('quality') or 'hq').strip().lower()
    allowed_qualities = {'maxres', 'sd', 'hq'}

    if len(video_id) != 11 or quality not in allowed_qualities:
        flash('Invalid thumbnail download request.')
        return redirect(url_for('index'), code=302)

    quality_to_file = {
        'maxres': 'maxresdefault.jpg',
        'sd': 'sddefault.jpg',
        'hq': 'hqdefault.jpg',
    }
    target_url = f"https://i.ytimg.com/vi/{video_id}/{quality_to_file[quality]}"

    try:
        response = requests.get(target_url, timeout=10, headers=YT_HTTP_HEADERS)
        if response.status_code >= 400:
            raise ValueError('Thumbnail unavailable')

        file_name = f"{video_id}-{quality}.jpg"
        return send_file(
            BytesIO(response.content),
            mimetype='image/jpeg',
            as_attachment=True,
            download_name=file_name,
        )
    except Exception:
        flash('Unable to download thumbnail in that resolution.')
        return redirect(url_for('index'), code=302)

@app.route('/robots.txt')
@app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


with app.app_context():
    db.create_all()
