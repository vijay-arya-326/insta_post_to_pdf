from __future__ import annotations

import re
import shutil
import tempfile
import time
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
    download_video,
    get_job_progress,
    playlist_library_dir,
    preview_video,
)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CACHE_TTL_SECONDS = 10 * 60
CACHE_VERSION = "orig-v3"

app = FastAPI(title="Instagram post to PDF")
_cache: dict[str, dict[str, Any]] = {}
_cache_lock = Lock()


class UrlBody(BaseModel):
    url: str = Field(min_length=8)


class YoutubeBody(BaseModel):
    url: str = Field(min_length=8)
    format: Literal["mp4", "mp3"] = "mp4"
    video_quality: str = "best"
    audio_quality: str = "192"
    filename: str = ""
    playlist_title: str = ""
    job_id: str = ""


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


@app.post("/api/youtube/preview")
async def youtube_preview(body: UrlBody) -> dict[str, Any]:
    try:
        info = await preview_video(body.url)
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
        )
    except YoutubeError as exc:
        cleanup()
        raise _youtube_http_error(exc) from exc

    filename = path.name
    media_type = "audio/mpeg" if body.format == "mp3" else "video/mp4"
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
