from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
import tempfile
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from instagram import InstagramError, download_images, extract_shortcode, resolve_post
from pdf import images_to_pdf, thumbnail_data_url
from youtube import (
    YoutubeError,
    available_options,
    cookie_file_info,
    delete_cookie_file,
    download_video,
    get_job_progress,
    playlist_library_dir,
    preview_video,
    save_cookie_file,
)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CACHE_TTL_SECONDS = 10 * 60
CACHE_VERSION = "orig-v3"

LOGS_DIR = ROOT / "logs"
LOG_FILE = LOGS_DIR / "app.log"
LOG_RETENTION_DAYS = 5

def _setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.namer = lambda name: name.replace(".log.", ".") + ".log"
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)

    # Also configure uvicorn loggers to use our handler
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.INFO)

    # Log system info at startup
    log = logging.getLogger("app")
    log.info("System: %s %s (%s) Python: %s", platform.system(), platform.release(), platform.machine(), platform.python_version())
    log.info("Architecture: %s, Processor: %s", platform.architecture()[0], platform.processor())

_setup_logging()
log = logging.getLogger("app")

app = FastAPI(title="Instagram post to PDF")
_cache: dict[str, dict[str, Any]] = {}
_cache_lock = Lock()


class UrlBody(BaseModel):
    url: str = Field(min_length=8)


class YoutubePreviewBody(BaseModel):
    url: str = Field(min_length=8)
    cookies_from_browser: str = ""
    cookies_file: str = ""


class YoutubeBody(BaseModel):
    url: str = Field(min_length=8)
    format: Literal["mp4", "webm", "mp3"] = "mp4"
    video_quality: str = "best"
    audio_quality: str = "192"
    filename: str = ""
    playlist_title: str = ""
    job_id: str = ""
    cookies_from_browser: str = ""
    cookies_file: str = ""


class CookieUploadBody(BaseModel):
    content: str = Field(min_length=1)


def pdf_filename(title: str | None, caption: str | None, shortcode: str) -> str:
    source = (title or "").strip()
    if source.lower() in {"", "na", "n/a", "unknown"}:
        source = ""
    if not source and caption:
        source = caption.strip().splitlines()[0].strip()
    source = re.sub(r"[\\/:*?\"<>|]+", " ", source)
    source = re.sub(r"\s+", " ", source).strip(" .")
    if len(source) > 80:
        source = source[:80].rstrip()
    if not source:
        source = shortcode
    return f"{source}.pdf"


def _disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip() or "instagram-post.pdf"
    ascii_name = ascii_name.replace('"', "")
    encoded = quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _purge_cache() -> None:
    now = time.time()
    expired = [key for key, value in _cache.items() if now - value["created"] > CACHE_TTL_SECONDS]
    for key in expired:
        _cache.pop(key, None)


def _put_cache(shortcode: str, images: list[bytes], caption: str | None, title: str | None) -> None:
    with _cache_lock:
        _purge_cache()
        _cache[f"{shortcode}:{CACHE_VERSION}"] = {
            "images": images,
            "caption": caption,
            "title": title,
            "created": time.time(),
        }


def _get_cache(shortcode: str) -> dict[str, Any] | None:
    with _cache_lock:
        _purge_cache()
        return _cache.get(f"{shortcode}:{CACHE_VERSION}")


async def _load_images(url: str) -> tuple[str, list[bytes], str | None, str | None]:
    try:
        shortcode = extract_shortcode(url)
    except InstagramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cached = _get_cache(shortcode)
    if cached:
        return shortcode, cached["images"], cached["caption"], cached.get("title")

    try:
        media = await resolve_post(url)
        images = await download_images(media.slides)
    except InstagramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not images:
        raise HTTPException(status_code=400, detail="That post has no photos to put in a PDF.")

    _put_cache(media.shortcode, images, media.caption, media.title)
    return media.shortcode, images, media.caption, media.title


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/preview")
async def preview(body: UrlBody) -> dict[str, Any]:
    shortcode, images, caption, title = await _load_images(body.url)
    slides = []
    for index, raw in enumerate(images, start=1):
        data_url, width, height = thumbnail_data_url(raw)
        slides.append({"index": index, "preview": data_url, "width": width, "height": height})
    return {
        "shortcode": shortcode,
        "title": title,
        "caption": caption,
        "count": len(slides),
        "slides": slides,
    }


@app.post("/api/pdf")
async def pdf(body: UrlBody) -> Response:
    shortcode, images, caption, title = await _load_images(body.url)
    try:
        pdf_bytes = images_to_pdf(images)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not build the PDF ({exc}).") from exc
    filename = pdf_filename(title, caption, shortcode)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _disposition(filename)},
    )


def _youtube_http_error(exc: YoutubeError) -> HTTPException:
    if exc.install:
        return HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "code": "ffmpeg_missing",
                "install": exc.install,
            },
        )
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/youtube/options")
async def youtube_options() -> dict[str, Any]:
    return available_options()


@app.get("/api/youtube/cookies")
async def youtube_cookies_status() -> dict[str, Any]:
    return cookie_file_info()


@app.post("/api/youtube/cookies")
async def youtube_cookies_upload(body: CookieUploadBody) -> dict[str, Any]:
    try:
        save_cookie_file(body.content)
    except YoutubeError as exc:
        raise _youtube_http_error(exc) from exc
    return cookie_file_info()


@app.delete("/api/youtube/cookies")
async def youtube_cookies_delete() -> dict[str, Any]:
    delete_cookie_file()
    return cookie_file_info()


@app.post("/api/youtube/preview")
async def youtube_preview(body: YoutubePreviewBody) -> dict[str, Any]:
    try:
        info = await preview_video(body.url, body.cookies_from_browser, body.cookies_file)
    except YoutubeError as exc:
        raise _youtube_http_error(exc) from exc
    return {
        "id": info.id,
        "title": info.title,
        "uploader": info.uploader,
        "duration": info.duration,
        "thumbnail": info.thumbnail,
        "url": info.webpage_url,
        "is_playlist": info.is_playlist,
        "count": len(info.entries) if info.entries else 1,
        "library_folder": str(playlist_library_dir(info.title)) if info.is_playlist or (info.entries and len(info.entries) > 1) else None,
        "entries": [
            {
                "id": entry.id,
                "title": entry.title,
                "url": entry.url,
                "duration": entry.duration,
                "thumbnail": entry.thumbnail,
            }
            for entry in info.entries
        ],
    }


@app.post("/api/youtube/download")
async def youtube_download(body: YoutubeBody) -> FileResponse:
    tmp = Path(tempfile.mkdtemp(prefix="yt-dlp-"))

    def cleanup() -> None:
        shutil.rmtree(tmp, ignore_errors=True)

    try:
        info, path = await download_video(
            body.url,
            tmp,
            body.format,
            body.video_quality,
            body.audio_quality,
            body.filename,
            cookies_browser=body.cookies_from_browser,
            cookies_file=body.cookies_file,
        )
    except YoutubeError as exc:
        cleanup()
        raise _youtube_http_error(exc) from exc

    filename = path.name
    if body.format == "mp3":
        media_type = "audio/mpeg"
    elif body.format == "webm":
        media_type = "video/webm"
    else:
        media_type = "video/mp4"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Content-Disposition": _disposition(filename)},
        background=BackgroundTask(cleanup),
    )


@app.post("/api/youtube/save")
async def youtube_save(body: YoutubeBody) -> dict[str, Any]:
    dest = playlist_library_dir(body.playlist_title or "YouTube playlist", create=True)
    try:
        info, path = await download_video(
            body.url,
            dest,
            body.format,
            body.video_quality,
            body.audio_quality,
            body.filename,
            body.job_id,
            body.cookies_from_browser,
            body.cookies_file,
        )
    except YoutubeError as exc:
        raise _youtube_http_error(exc) from exc
    return {
        "ok": True,
        "title": info.title,
        "path": str(path),
        "folder": str(dest),
        "filename": path.name,
    }


@app.get("/api/youtube/job/{job_id}")
async def youtube_job(job_id: str) -> dict[str, Any]:
    return get_job_progress(job_id)


def _run_git(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "git is not installed."
    except subprocess.TimeoutExpired:
        return False, f"git {' '.join(args)} timed out."
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, err or out or f"git {' '.join(args)} failed."
    return True, out


@app.get("/api/update/check")
async def update_check() -> dict[str, Any]:
    ok, out = _run_git(["rev-parse", "--show-toplevel"])
    if not ok:
        return {"ok": False, "update_available": False, "error": "Not a git checkout."}
    ok, branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if not ok:
        return {"ok": False, "update_available": False, "error": branch}
    branch = branch.strip() or "main"
    ok, current = _run_git(["rev-parse", "HEAD"])
    if not ok:
        return {"ok": False, "update_available": False, "error": current}
    current = current.strip()

    # Best-effort fetch so the check reflects the remote. Offline -> keep going
    # with the last-fetched remote ref.
    fetch_ok, fetch_out = _run_git(["fetch", "origin"], timeout=20)
    fetch_error = None if fetch_ok else fetch_out

    upstream = f"origin/{branch}"
    ok, upstream_ref = _run_git(["rev-parse", "--verify", upstream])
    if not ok:
        # Fall back to whatever upstream is configured, if any.
        ok, configured = _run_git(["rev-parse", "--abbrev-ref", "@{u}"])
        if ok and configured:
            upstream = configured.strip()
            ok, upstream_ref = _run_git(["rev-parse", "--verify", upstream])
        if not ok:
            return {
                "ok": False,
                "update_available": False,
                "branch": branch,
                "current": current,
                "error": f"Remote branch {upstream} not found.",
                "fetch_error": fetch_error,
            }
    remote = upstream_ref.strip()

    ok, behind_out = _run_git(["rev-list", "--count", f"HEAD..{upstream}"])
    behind = int(behind_out.strip()) if ok and behind_out.strip().isdigit() else 0
    ok, ahead_out = _run_git(["rev-list", "--count", f"{upstream}..HEAD"])
    ahead = int(ahead_out.strip()) if ok and ahead_out.strip().isdigit() else 0
    ok, log_out = _run_git(["log", "--oneline", "-10", f"HEAD..{upstream}"])
    commits = log_out.splitlines() if ok and log_out else []
    ok, dirty_out = _run_git(["status", "--porcelain"])
    dirty = bool(ok and dirty_out.strip())

    return {
        "ok": True,
        "update_available": behind > 0,
        "behind": behind,
        "ahead": ahead,
        "branch": branch,
        "upstream": upstream,
        "current": current,
        "latest": remote,
        "commits": commits,
        "dirty": dirty,
        "fetch_error": fetch_error,
        "repo": "https://github.com/vijay-arya-326/insta_post_to_pdf.git",
    }


@app.post("/api/update/apply")
async def update_apply() -> dict[str, Any]:
    ok, dirty_out = _run_git(["status", "--porcelain"])
    if ok and dirty_out.strip():
        raise HTTPException(
            status_code=409,
            detail="You have local changes. Commit or stash them before updating.",
        )
    ok, out = _run_git(["pull", "--ff-only"], timeout=120)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Update failed: {out}")
    _, new_head = _run_git(["rev-parse", "HEAD"])
    return {"ok": True, "output": out, "current": new_head.strip()}
