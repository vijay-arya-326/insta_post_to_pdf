from __future__ import annotations

import asyncio
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "music.youtube.com")

VIDEO_QUALITIES = (
    {"id": "best", "label": "Best available", "help": "Highest video and audio yt-dlp can merge to MP4"},
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
    {"id": "mp3", "label": "MP3 audio", "help": "Audio only, converted to MP3 (needs ffmpeg)"},
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


def ffmpeg_missing_error() -> YoutubeError:
    return YoutubeError(
        "ffmpeg is required for MP4 merge and MP3 conversion.",
        install=ffmpeg_install_guide(),
    )


@dataclass
class YoutubeInfo:
    id: str
    title: str
    uploader: str | None
    duration: int | None
    thumbnail: str | None
    webpage_url: str


def available_options() -> dict:
    return {
        "formats": list(FORMATS),
        "video_quality": list(VIDEO_QUALITIES),
        "audio_quality": list(AUDIO_QUALITIES),
        "notes": [
            "Uses yt-dlp. Playlist links download only the first / linked video.",
            "MP4 merge and MP3 conversion need ffmpeg on PATH.",
            "Best MP4 prefers mp4/m4a streams, then remuxes other codecs into MP4.",
        ],
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffmpeg_install": ffmpeg_install_guide(),
    }


def assert_youtube_url(url: str) -> str:
    text = url.strip()
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if not any(host == item or host.endswith("." + item) for item in YOUTUBE_HOSTS):
        raise YoutubeError("Paste a YouTube video URL.")
    return text


def _format_selector(kind: str, video_quality: str) -> str:
    if kind == "mp3":
        return "bestaudio/best"
    height = None if video_quality == "best" else video_quality
    if height:
        return (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}][ext=mp4]/best[height<={height}]"
        )
    return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"


def _base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
    }


def _extract_sync(url: str) -> dict:
    opts = {**_base_opts(), "skip_download": True, "ignore_no_formats_error": True}
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _download_sync(
    url: str, dest_dir: Path, kind: str, video_quality: str, audio_quality: str
) -> tuple[dict, Path]:
    if kind in {"mp4", "mp3"} and not shutil.which("ffmpeg"):
        raise ffmpeg_missing_error()

    dest_dir.mkdir(parents=True, exist_ok=True)
    # Use the video id only. User titles can contain % and other
    # characters that yt-dlp treats as output-template syntax.
    outtmpl = str(dest_dir / "%(id)s.%(ext)s")
    opts: dict = {
        **_base_opts(),
        "format": _format_selector(kind, video_quality),
        "outtmpl": outtmpl,
        "restrictfilenames": True,
    }
    if kind == "mp4":
        opts["merge_output_format"] = "mp4"
        opts["final_ext"] = "mp4"
        opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]
    else:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio_quality,
            }
        ]

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise YoutubeError("Could not download that video.")
        prepared = ydl.prepare_filename(info)
        video_id = str(info.get("id") or "")
        expected_ext = "mp3" if kind == "mp3" else "mp4"
        candidates = [
            Path(prepared).with_suffix(f".{expected_ext}"),
            dest_dir / f"{video_id}.{expected_ext}",
            Path(prepared),
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                return info, path
        matches = sorted(dest_dir.glob(f"{video_id}.*")) if video_id else list(dest_dir.iterdir())
        files = [p for p in matches if p.is_file()]
        if not files:
            raise YoutubeError("Download finished but the file was not found.")
        return info, files[0]


def _info_from_raw(info: dict) -> YoutubeInfo:
    if info.get("_type") == "playlist":
        entries = [entry for entry in (info.get("entries") or []) if entry]
        if not entries:
            raise YoutubeError("That playlist has no videos.")
        info = entries[0]
    video_id = str(info.get("id") or "")
    title = str(info.get("title") or video_id or "YouTube video")
    if not video_id:
        raise YoutubeError("Could not read that YouTube video.")
    return YoutubeInfo(
        id=video_id,
        title=title,
        uploader=info.get("uploader") or info.get("channel"),
        duration=info.get("duration") if isinstance(info.get("duration"), int) else None,
        thumbnail=info.get("thumbnail"),
        webpage_url=str(info.get("webpage_url") or ""),
    )


async def preview_video(url: str) -> YoutubeInfo:
    url = assert_youtube_url(url)
    try:
        info = await asyncio.to_thread(_extract_sync, url)
    except (DownloadError, ExtractorError) as exc:
        raise _from_ydl_error(exc) from exc
    except YoutubeError:
        raise
    except Exception as exc:
        raise YoutubeError("Could not load that YouTube video.") from exc
    if not info:
        raise YoutubeError("Could not load that YouTube video.")
    return _info_from_raw(info)


async def download_video(
    url: str,
    dest_dir: Path,
    kind: str,
    video_quality: str,
    audio_quality: str,
    output_name: str = "",
) -> tuple[YoutubeInfo, Path]:
    url = assert_youtube_url(url)
    if kind not in {"mp4", "mp3"}:
        raise YoutubeError("Format must be mp4 or mp3.")
    allowed_video = {item["id"] for item in VIDEO_QUALITIES}
    allowed_audio = {item["id"] for item in AUDIO_QUALITIES}
    if video_quality not in allowed_video:
        raise YoutubeError("Unknown video quality.")
    if audio_quality not in allowed_audio:
        raise YoutubeError("Unknown audio quality.")
    try:
        info, path = await asyncio.to_thread(
            _download_sync, url, dest_dir, kind, video_quality, audio_quality
        )
        meta = _info_from_raw(info)
    except YoutubeError:
        raise
    except (DownloadError, ExtractorError) as exc:
        raise _from_ydl_error(exc) from exc
    except Exception as exc:
        if "ffmpeg" in str(exc).lower():
            raise ffmpeg_missing_error() from exc
        raise YoutubeError(f"Could not download that video ({exc}).") from exc
    ext = "mp3" if kind == "mp3" else "mp4"
    final_name = sanitize_download_name(output_name or meta.title, ext)
    final_path = dest_dir / final_name
    if path.resolve() != final_path.resolve():
        if final_path.exists():
            final_path.unlink()
        path = path.replace(final_path)
    return meta, path


def _from_ydl_error(exc: BaseException) -> YoutubeError:
    message = str(exc).lower()
    if "ffmpeg" in message:
        return ffmpeg_missing_error()
    if "sign in" in message or "age" in message or "confirm your age" in message:
        return YoutubeError("That video is age-restricted or needs a sign-in.")
    if "private" in message:
        return YoutubeError("That video is private.")
    return YoutubeError("Could not download that YouTube video.")


_SAFE_NAME = re.compile(r"[\\/:*?\"<>|]+")


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
