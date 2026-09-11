from __future__ import annotations

import re
import time
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from instagram import InstagramError, download_images, extract_shortcode, resolve_post
from pdf import images_to_pdf, thumbnail_data_url

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CACHE_TTL_SECONDS = 10 * 60
CACHE_VERSION = "orig-v3"

app = FastAPI(title="Instagram post to PDF")
_cache: dict[str, dict[str, Any]] = {}
_cache_lock = Lock()


class UrlBody(BaseModel):
    url: str = Field(min_length=8)


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
