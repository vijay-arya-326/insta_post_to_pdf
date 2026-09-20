from __future__ import annotations

import asyncio
import logging
import platform
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

log = logging.getLogger("app")

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "music.youtube.com")
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = Lock()

VIDEO_QUALITIES = (
    {"id": "best", "label": "Best available", "help": "Highest video and audio yt-dlp can merge"},
    {"id": "1080", "label": "1080p", "help": "Cap height at 1080, then pick the best stream"},
    {"id": "720", "label": "720p", "help": "Cap height at 720, then pick the best stream"},
    {"id": "480", "label": "480p", "help": "Cap height at 480, then pick the best stream"},
)

AUDIO_QUALITIES = (
    {"id": "320", "label": "320 kbps", "help": "Highest common MP3 bitrate"},
    {"id": "256", "label": "256 kbps", "help": "Balanced size and quality"},
    {"id": "192", "label": "192 kbps", "help": "Smaller file"},
)

FORMATS = (
    {"id": "mp4", "label": "MP4 video", "help": "Best video + audio merged into MP4 (needs ffmpeg)"},
    {"id": "webm", "label": "WebM video", "help": "Best VP9/Opus streams merged into WebM (needs ffmpeg)"},
    {"id": "mp3", "label": "MP3 audio", "help": "Audio only, converted to MP3 (needs ffmpeg)"},
)
VIDEO_KINDS = {"mp4", "webm"}
AUDIO_KINDS = {"mp3"}
COOKIE_BROWSERS = (
    {"id": "chrome", "label": "Chrome"},
    {"id": "safari", "label": "Safari"},
    {"id": "firefox", "label": "Firefox"},
    {"id": "edge", "label": "Edge"},
    {"id": "brave", "label": "Brave"},
    {"id": "chromium", "label": "Chromium"},
    {"id": "none", "label": "None"},
)


class YoutubeError(Exception):
    def __init__(self, message: str, *, install: dict | None = None):
        super().__init__(message)
        self.install = install


def ffmpeg_install_guide() -> dict[str, str | list[str]]:
    system = platform.system().lower()
    if system == "windows":
        return {
            "os": "Windows",
            "command": "winget install Gyan.FFmpeg",
            "steps": [
                "Open PowerShell or Windows Terminal.",
                "Run: winget install Gyan.FFmpeg",
                "If winget is unavailable, install from https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-essentials.zip) and add the bin folder to PATH.",
                "Close this app completely, then start it again so it picks up PATH.",
                "Check with: ffmpeg -version",
            ],
        }
    if system == "darwin":
        return {
            "os": "macOS",
            "command": "brew install ffmpeg",
            "steps": [
                "Install Homebrew if needed: https://brew.sh",
                "Run: brew install ffmpeg",
                "Restart this app.",
                "Check with: ffmpeg -version",
            ],
        }
    return {
        "os": "Linux",
        "command": "sudo apt update && sudo apt install ffmpeg",
        "steps": [
            "Debian/Ubuntu: sudo apt update && sudo apt install ffmpeg",
            "Fedora: sudo dnf install ffmpeg",
            "Arch: sudo pacman -S ffmpeg",
            "Restart this app.",
            "Check with: ffmpeg -version",
        ],
    }


def deno_install_guide() -> dict[str, str | list[str]]:
    system = platform.system().lower()
    if system == "windows":
        return {
            "os": "Windows",
            "command": "winget install denoland.deno",
            "steps": [
                "Open PowerShell or Windows Terminal.",
                "Run: winget install denoland.deno",
                "If winget is unavailable, install from https://deno.land/#installation and add to PATH.",
                "Close this app completely, then start it again so it picks up PATH.",
                "Check with: deno --version",
            ],
        }
    if system == "darwin":
        return {
            "os": "macOS",
            "command": "brew install deno",
            "steps": [
                "Install Homebrew if needed: https://brew.sh",
                "Run: brew install deno",
                "Restart this app.",
                "Check with: deno --version",
            ],
        }
    return {
        "os": "Linux",
        "command": "curl -fsSL https://deno.land/install.sh | sh",
        "steps": [
            "Run: curl -fsSL https://deno.land/install.sh | sh",
            "Add deno to PATH (usually ~/.deno/bin).",
            "Restart this app.",
            "Check with: deno --version",
        ],
    }


def deno_missing_error() -> YoutubeError:
    return YoutubeError(
        "deno is required for YouTube signature decryption (JS challenge).",
        install=deno_install_guide(),
    )


def set_job_progress(job_id: str, **fields: object) -> None:
    if not job_id:
        return
    with _JOBS_LOCK:
        current = dict(_JOBS.get(job_id) or {})
        current.update(fields)
        _JOBS[job_id] = current


def get_job_progress(job_id: str) -> dict:
    with _JOBS_LOCK:
        return dict(_JOBS.get(job_id) or {})


def _ffmpeg_label(postprocessor: str) -> str:
    name = (postprocessor or "").lower()
    if "extractaudio" in name:
        return "Converting audio with ffmpeg"
    if "remux" in name or "merger" in name or "convert" in name:
        return "Merging with ffmpeg"
    if "ffmpeg" in name or "fixup" in name:
        return "Processing with ffmpeg"
    if postprocessor:
        return f"Processing ({postprocessor})"
    return "Processing with ffmpeg"


def _progress_hook(job_id: str):
    def hook(data: dict) -> None:
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = round(downloaded * 100 / total, 1) if total else None
            speed = str(data.get("_speed_str") or "").strip()
            detail = "Downloading"
            if percent is not None:
                detail = f"Downloading {percent:.0f}%"
            if speed and speed != "NA":
                detail = f"{detail} ({speed})"
            set_job_progress(job_id, phase="downloading", label=detail, percent=percent)
        elif status == "finished":
            set_job_progress(
                job_id,
                phase="processing",
                label="Processing with ffmpeg",
                percent=None,
            )
        elif status == "error":
            set_job_progress(job_id, phase="error", label="Download error")

    return hook


def _postprocessor_hook(job_id: str):
    def hook(data: dict) -> None:
        status = data.get("status")
        label = _ffmpeg_label(str(data.get("postprocessor") or ""))
        if status in {"started", "processing"}:
            set_job_progress(job_id, phase="processing", label=label)
        elif status == "finished":
            set_job_progress(job_id, phase="saving", label="Saving file")

    return hook


def ffmpeg_missing_error() -> YoutubeError:
    return YoutubeError(
        "ffmpeg is required for MP4/WebM merge and MP3 conversion.",
        install=ffmpeg_install_guide(),
    )


def cookies_help(browser: str = "chrome") -> dict[str, str | list[str]]:
    name = (browser or "chrome").strip() or "chrome"
    label = name.title()
    return {
        "os": platform.system(),
        "command": f"Sign in to YouTube in {label}, then retry Preview / Download.",
        "steps": [
            f"Open {label} and sign in at youtube.com (use the same profile you download with).",
            "In this app, set YouTube cookies to that browser.",
            "macOS may ask for Keychain access — choose Allow.",
            "If cookie copy fails, fully quit that browser and try again (common with Firefox).",
            "Preview or Download again.",
        ],
    }


def cookies_needed_error(browser: str = "") -> YoutubeError:
    chosen = browser or "chrome"
    return YoutubeError(
        "YouTube asked to confirm you are not a bot. Sign in to YouTube in your browser, pick that browser under YouTube cookies, and try again.",
        install=cookies_help(chosen),
    )


def normalize_cookie_browser(name: str) -> str:
    text = (name or "").strip().lower()
    if text in {"", "none", "off"}:
        return ""
    allowed = {item["id"] for item in COOKIE_BROWSERS if item["id"] != "none"}
    if text not in allowed:
        raise YoutubeError("Unknown browser for YouTube cookies.")
    return text


UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
UPLOADED_COOKIE_FILE = UPLOADS_DIR / "cookie.txt"


def save_cookie_file(content: str) -> Path | None:
    """Save (overwrite) the uploaded cookie file as ``uploads/cookie.txt``."""
    content = (content or "").strip()
    if not content:
        return None
    if len(content) > 2_000_000:
        raise YoutubeError("Cookie file is too large.")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # Normalize line endings to LF for yt-dlp compatibility on Windows
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    UPLOADED_COOKIE_FILE.write_text(content, encoding="utf-8", newline="\n")
    return UPLOADED_COOKIE_FILE


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def cookie_file_info() -> dict:
    p = UPLOADED_COOKIE_FILE
    empty = {
        "exists": False,
        "file": "",
        "size": 0,
        "count": 0,
        "modified": None,
        "identity": None,
        "content": "",
    }
    if not p.is_file():
        return empty
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return empty
    count = 0
    emails: list[str] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        count += 1
        emails.extend(_EMAIL_RE.findall(line))
    stat = p.stat()
    return {
        "exists": True,
        "file": p.name,
        "size": stat.st_size,
        "count": count,
        "modified": stat.st_mtime,
        "identity": sorted(set(emails))[0] if emails else None,
        "content": text,
    }


def delete_cookie_file() -> bool:
    UPLOADED_COOKIE_FILE.unlink(missing_ok=True)
    return not UPLOADED_COOKIE_FILE.exists()


def _cookie_opts(browser: str = "", cookies_file: str = "") -> dict:
    if cookies_file:
        return {"cookies": cookies_file}
    if not browser:
        return {}
    return {"cookiesfrombrowser": (browser,)}


def _needs_youtube_cookies(message: str) -> bool:
    return any(
        needle in message
        for needle in (
            "not a bot",
            "cookies-from-browser",
            "cookies for the authentication",
            "--cookies",
            "could not copy",
            "failed to decrypt",
            "failed to load cookies",
            "unable to load cookies",
        )
    )


@dataclass
class YoutubeEntry:
    id: str
    title: str
    url: str
    duration: int | None = None
    thumbnail: str | None = None


@dataclass
class YoutubeInfo:
    id: str
    title: str
    uploader: str | None
    duration: int | None
    thumbnail: str | None
    webpage_url: str
    is_playlist: bool = False
    entries: list[YoutubeEntry] = field(default_factory=list)


def available_options() -> dict:
    return {
        "formats": list(FORMATS),
        "video_quality": list(VIDEO_QUALITIES),
        "audio_quality": list(AUDIO_QUALITIES),
        "notes": [
            "Playlists save directly into the project download folder. Each video finishes before the next starts. Each video finishes before the next starts.",
            "MP4/WebM merge and MP3 conversion need ffmpeg on PATH.",
            "Best MP4 prefers mp4/m4a streams. Best WebM prefers webm/opus streams.",
            "YouTube may ask for a sign-in. Use YouTube cookies from the browser where you are logged in.",
        ],
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffmpeg_install": ffmpeg_install_guide(),
        "cookie_browsers": list(COOKIE_BROWSERS),
        "cookie_browser_default": "chrome",
        "library_root": str(user_videos_library()),
    }


def playlist_id_from_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    values = parse_qs(parsed.query).get("list") or []
    playlist_id = (values[0] if values else "").strip()
    if playlist_id:
        return playlist_id
    return None


def playlist_page_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def assert_youtube_url(url: str) -> str:
    text = url.strip()
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if not any(host == item or host.endswith("." + item) for item in YOUTUBE_HOSTS):
        raise YoutubeError("Paste a YouTube video URL.")
    return text


def _kind_ext(kind: str) -> str:
    if kind == "mp3":
        return "mp3"
    if kind == "webm":
        return "webm"
    return "mp4"


def _format_selector(kind: str, video_quality: str) -> str:
    """Build a yt-dlp format selector that always includes audio.

    Primary: ``bestvideo+bestaudio`` — strictly matches video-only + audio-only
    streams so yt-dlp always merges two separate tracks via ffmpeg.
    Fallback: ``best`` (NOT ``best*``) — ``best`` = combined video+audio;
    ``best*`` = "best video" which can be video-only (no audio).
    """
    if kind == "mp3":
        return "bestaudio/best"
    height = None if video_quality == "best" else video_quality
    if height:
        return (
            # Strictly video-only + audio-only → always two-track merge
            f"bestvideo[height<={height}]+bestaudio/"
            # Wider fallback (any ext) still requiring two tracks
            f"bestvideo*[height<={height}]+bestaudio*/"
            # Combined format within height cap (has both video+audio)
            f"best[height<={height}]/"
            # Absolute fallback — always has both video+audio
            "best"
        )
    return "bestvideo+bestaudio/bestvideo*+bestaudio*/best"


def _base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
        # Enable the EJS JS-challenge solver (runs via deno).
        # Without this, YouTube's signature/n-challenge decryption fails and
        # yt-dlp only returns storyboard thumbnails — every format selector
        # then raises "Requested format is not available".
        # The solver script is downloaded from GitHub on first use and cached.
        "allow_unplayable_formats": False,
        # web_embedded MUST stay first: with signed-in cookies, web_creator/tv
        # are rejected by YouTube ("Please sign in...") while web_embedded works.
        # web_embedded alone also handles the signed-out case without PO-token.
        "extractor_args": {
            "youtube": {"player_client": ["web_embedded", "web_creator", "tv"]}
        },
        "remote_components": ["ejs:github"],
        # Impersonate Chrome to bypass bot detection (recommended by yt-dlp FAQ)
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Sec-Fetch-Mode": "navigate",
        },
    }


def _extract_sync(
    url: str,
    *,
    allow_playlist: bool = False,
    extract_flat: bool = False,
    cookies_browser: str = "",
    cookies_file: str = "",
) -> dict:
    saved = save_cookie_file(cookies_file)
    opts = {
        **_base_opts(),
        "skip_download": True,
        "ignore_no_formats_error": True,
        "noplaylist": not allow_playlist,
        "ignoreerrors": allow_playlist,
        **_cookie_opts(cookies_browser, str(saved) if saved else ""),
    }
    if extract_flat:
        opts["extract_flat"] = True
    log.info("Preview extract: url=%s allow_playlist=%s extract_flat=%s cookies_browser=%s has_cookie_file=%s",
             url, allow_playlist, extract_flat, cookies_browser, bool(saved))
    with YoutubeDL(opts) as ydl:
        result = ydl.extract_info(url, download=False)
        log.info("Preview extract done: type=%s id=%s", result.get("_type"), result.get("id") or result.get("title", "?"))
        return result


def _download_sync(
    url: str,
    dest_dir: Path,
    kind: str,
    video_quality: str,
    audio_quality: str,
    job_id: str = "",
    cookies_browser: str = "",
    cookies_file: str = "",
) -> tuple[dict, Path]:
    if kind in VIDEO_KINDS | AUDIO_KINDS and not shutil.which("ffmpeg"):
        raise ffmpeg_missing_error()
    if not shutil.which("deno"):
        raise deno_missing_error()

    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / "%(id)s.%(ext)s")
    saved = save_cookie_file(cookies_file)
    return _download_sync_with_opts(
        url,
        dest_dir,
        kind,
        video_quality,
        audio_quality,
        job_id,
        outtmpl,
        cookies_browser,
        str(saved) if saved else "",
    )


def _download_sync_with_opts(
    url: str,
    dest_dir: Path,
    kind: str,
    video_quality: str,
    audio_quality: str,
    job_id: str,
    outtmpl: str,
    cookies_browser: str,
    cookies_file: str,
) -> tuple[dict, Path]:
    opts: dict = {
        **_base_opts(),
        "format": _format_selector(kind, video_quality),
        "outtmpl": outtmpl,
        "restrictfilenames": True,
        "noprogress": not bool(job_id),
        "no_color": True,
        **_cookie_opts(cookies_browser, cookies_file),
    }
    log.info("Download opts: kind=%s quality=%s format=%s cookies_browser=%s has_cookie_file=%s",
             kind, video_quality, opts["format"], cookies_browser, bool(cookies_file))
    if job_id:
        set_job_progress(job_id, phase="starting", label="Starting download")
        opts["progress_hooks"] = [_progress_hook(job_id)]
        opts["postprocessor_hooks"] = [_postprocessor_hook(job_id)]
    if kind in VIDEO_KINDS:
        opts["merge_output_format"] = kind
        opts["final_ext"] = kind
        opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": kind}]
        log.info("Video download: will merge to %s via ffmpeg", kind)
    else:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio_quality,
            }
        ]
        log.info("Audio download: will extract to mp3 %s kbps via ffmpeg", audio_quality)

    log.info("Starting yt-dlp extract_info for %s", url)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise YoutubeError("Could not download that video.")
        log.info("yt-dlp finished, info id=%s title=%s", info.get("id"), info.get("title"))
        prepared = ydl.prepare_filename(info)
        video_id = str(info.get("id") or "")
        expected_ext = _kind_ext(kind)
        candidates = [
            Path(prepared).with_suffix(f".{expected_ext}"),
            dest_dir / f"{video_id}.{expected_ext}",
            Path(prepared),
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                log.info("Found output file: %s (%.1f MB)", path, path.stat().st_size / 1024 / 1024)
                return info, path
        matches = sorted(dest_dir.glob(f"{video_id}.*")) if video_id else list(dest_dir.iterdir())
        files = [p for p in matches if p.is_file()]
        if not files:
            log.error("No output file found in %s for video_id=%s", dest_dir, video_id)
            raise YoutubeError("Download finished but the file was not found.")
        log.info("Found output file (fallback): %s", files[0])
        return info, files[0]


def _watch_url(video_id: str, entry: dict | None = None) -> str:
    if entry:
        webpage = str(entry.get("webpage_url") or "")
        if "watch?v=" in webpage or "youtu.be/" in webpage:
            return webpage
        raw = str(entry.get("url") or "")
        if raw.startswith("http") and ("watch?v=" in raw or "youtu.be/" in raw):
            return raw
    return f"https://www.youtube.com/watch?v={video_id}"


def _duration(value: object) -> int | None:
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


def _entry_from_raw(entry: dict | None) -> YoutubeEntry | None:
    if not entry or entry.get("_type") == "playlist":
        return None
    video_id = str(entry.get("id") or "").strip()
    title = str(entry.get("title") or "").strip()
    if not video_id or title.lower() in {"[deleted video]", "[private video]", "[unavailable]"}:
        return None
    thumb = entry.get("thumbnail")
    if not thumb:
        thumbs = entry.get("thumbnails") or []
        if thumbs:
            thumb = thumbs[-1].get("url")
    return YoutubeEntry(
        id=video_id,
        title=title or video_id,
        url=_watch_url(video_id, entry),
        duration=_duration(entry.get("duration")),
        thumbnail=thumb,
    )


def _info_from_raw(info: dict) -> YoutubeInfo:
    if info.get("_type") == "playlist":
        entries = [_entry_from_raw(entry) for entry in (info.get("entries") or [])]
        entries = [entry for entry in entries if entry]
        if not entries:
            raise YoutubeError("That playlist has no videos.")
        playlist_id = str(info.get("id") or entries[0].id)
        return YoutubeInfo(
            id=playlist_id,
            title=str(info.get("title") or "YouTube playlist"),
            uploader=info.get("uploader") or info.get("channel"),
            duration=None,
            thumbnail=info.get("thumbnail") or entries[0].thumbnail,
            webpage_url=str(info.get("webpage_url") or ""),
            is_playlist=True,
            entries=entries,
        )
    entry = _entry_from_raw(info)
    if not entry:
        raise YoutubeError("Could not read that YouTube video.")
    return YoutubeInfo(
        id=entry.id,
        title=entry.title,
        uploader=info.get("uploader") or info.get("channel"),
        duration=entry.duration,
        thumbnail=entry.thumbnail,
        webpage_url=entry.url,
        is_playlist=False,
        entries=[entry],
    )


async def preview_video(
    url: str, cookies_browser: str = "", cookies_file: str = ""
) -> YoutubeInfo:
    url = assert_youtube_url(url)
    cookies_browser = normalize_cookie_browser(cookies_browser)
    playlist_id = playlist_id_from_url(url)
    extract_url = playlist_page_url(playlist_id) if playlist_id else url
    log.info("Starting preview: url=%s browser=%s has_cookie_file=%s", url, cookies_browser, bool(cookies_file))
    try:
        info = await asyncio.to_thread(
            _extract_sync,
            extract_url,
            allow_playlist=True,
            extract_flat=True,
            cookies_browser=cookies_browser,
            cookies_file=cookies_file,
        )
        if playlist_id and (not info or info.get("_type") != "playlist"):
            info = await asyncio.to_thread(
                _extract_sync,
                url,
                allow_playlist=True,
                extract_flat=True,
                cookies_browser=cookies_browser,
                cookies_file=cookies_file,
            )
    except (DownloadError, ExtractorError) as exc:
        log.exception("Preview failed (yt-dlp error): url=%s error=%s", url, exc)
        if extract_url != url:
            try:
                info = await asyncio.to_thread(
                    _extract_sync,
                    url,
                    allow_playlist=True,
                    extract_flat=True,
                    cookies_browser=cookies_browser,
                    cookies_file=cookies_file,
                )
            except Exception:
                raise _from_ydl_error(exc, cookies_browser) from exc
        else:
            raise _from_ydl_error(exc, cookies_browser) from exc
    except YoutubeError:
        log.warning("Preview failed (YoutubeError): url=%s", url)
        raise
    except Exception as exc:
        log.exception("Preview failed (unexpected error): url=%s error=%s", url, exc)
        if _needs_youtube_cookies(str(exc).lower()):
            raise cookies_needed_error(cookies_browser) from exc
        raise YoutubeError("Could not load that YouTube video.") from exc
    if not info:
        log.warning("Preview returned no info: url=%s", url)
        raise YoutubeError("Could not load that YouTube video.")
    result = _info_from_raw(info)
    log.info("Preview completed: url=%s title=%s entries=%d", url, result.title, len(result.entries))
    return result


async def download_video(
    url: str,
    dest_dir: Path,
    kind: str,
    video_quality: str,
    audio_quality: str,
    output_name: str = "",
    job_id: str = "",
    cookies_browser: str = "",
    cookies_file: str = "",
) -> tuple[YoutubeInfo, Path]:
    url = assert_youtube_url(url)
    cookies_browser = normalize_cookie_browser(cookies_browser)
    if kind not in VIDEO_KINDS | AUDIO_KINDS:
        raise YoutubeError("Format must be mp4, webm, or mp3.")
    allowed_video = {item["id"] for item in VIDEO_QUALITIES}
    allowed_audio = {item["id"] for item in AUDIO_QUALITIES}
    if video_quality not in allowed_video:
        raise YoutubeError("Unknown video quality.")
    if audio_quality not in allowed_audio:
        raise YoutubeError("Unknown audio quality.")
    log.info("Starting download: url=%s kind=%s quality=%s browser=%s has_cookie_file=%s",
             url, kind, video_quality, cookies_browser, bool(cookies_file))
    try:
        info, path = await asyncio.to_thread(
            _download_sync,
            url,
            dest_dir,
            kind,
            video_quality,
            audio_quality,
            job_id,
            cookies_browser,
            cookies_file,
        )
        meta = _info_from_raw(info)
        log.info("Download completed: url=%s path=%s", url, path)
    except YoutubeError:
        log.warning("Download failed (YoutubeError): url=%s", url)
        raise
    except (DownloadError, ExtractorError) as exc:
        log.exception("Download failed (yt-dlp error): url=%s error=%s", url, exc)
        raise _from_ydl_error(exc, cookies_browser) from exc
    except Exception as exc:
        log.exception("Download failed (unexpected error): url=%s error=%s", url, exc)
        if "ffmpeg" in str(exc).lower():
            raise ffmpeg_missing_error() from exc
        if _needs_youtube_cookies(str(exc).lower()):
            raise cookies_needed_error(cookies_browser) from exc
        raise YoutubeError(f"Could not download that video ({exc}).") from exc
    ext = _kind_ext(kind)
    final_name = sanitize_download_name(output_name or meta.title, ext)
    final_path = dest_dir / final_name
    if path.resolve() != final_path.resolve():
        if final_path.exists():
            final_path.unlink()
        path = path.replace(final_path)
    if job_id:
        set_job_progress(job_id, phase="complete", label="Saved")
    return meta, path


def _from_ydl_error(exc: BaseException, cookies_browser: str = "") -> YoutubeError:
    raw = str(exc)
    message = raw.lower()
    log.warning("yt-dlp error converted: %s", raw[:500])
    if "ffmpeg" in message:
        return ffmpeg_missing_error()
    if _needs_youtube_cookies(message):
        return cookies_needed_error(cookies_browser)
    if "age" in message or "confirm your age" in message:
        return YoutubeError("That video is age-restricted or needs a sign-in.")
    if "private" in message:
        return YoutubeError("That video is private.")
    if "requested format is not available" in message or "no video formats found" in message:
        return YoutubeError(
            "No downloadable format was found for that video. "
            "It may be a live stream, a members-only video, or a region-restricted upload."
        )
    snippet = raw[:200].rstrip(".")
    return YoutubeError(f"Could not download that YouTube video: {snippet}")


_SAFE_NAME = re.compile(r"[\\/:*?\"<>|]+")


def sanitize_folder_name(name: str) -> str:
    source = name.strip()
    source = _SAFE_NAME.sub(" ", source)
    source = source.replace("%", "")
    source = re.sub(r"\s+", " ", source).strip(" .")
    if len(source) > 80:
        source = source[:80].rstrip(" .")
    return source or "YouTube playlist"


def user_videos_library() -> Path:
    # Return project download folder instead of system videos folder
    return Path(__file__).resolve().parent / "download"


def playlist_library_dir(playlist_title: str, *, create: bool = False) -> Path:
    # Use project download folder directly (no playlist name subfolder)
    dest = user_videos_library().joinpath(sanitize_folder_name(playlist_title))
    if create:
        dest.mkdir(parents=True, exist_ok=True)
    return dest


def sanitize_download_name(name: str, ext: str) -> str:
    source = name.strip()
    source = _SAFE_NAME.sub(" ", source)
    source = source.replace("%", "")
    source = re.sub(r"\s+", " ", source).strip(" .")
    suffix = f".{ext}"
    if source.lower().endswith(suffix):
        source = source[: -len(suffix)].strip(" .")
    if len(source) > 80:
        source = source[:80].rstrip(" .")
    if not source:
        source = "youtube-video"
    return f"{source}{suffix}"
