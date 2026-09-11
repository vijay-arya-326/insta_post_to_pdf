from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from pdf import enhance_image

SHORTCODE_RE = re.compile(
    r"(?:instagram\.com|instagr\.am)/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "ignore_no_formats_error": True,
    "skip_download": True,
    "noplaylist": False,
}


class InstagramError(Exception):
    pass


@dataclass
class Slide:
    url: str
    img_index: int = 1


@dataclass
class PostMedia:
    shortcode: str
    slides: list[Slide] = field(default_factory=list)
    caption: str | None = None
    title: str | None = None


def extract_shortcode(url: str) -> str:
    text = url.strip()
    match = SHORTCODE_RE.search(text)
    if match:
        return match.group(1)
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    if "instagram.com" in host or "instagr.am" in host:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9_-]{5,}", parts[0]):
            return parts[0]
    raise InstagramError("Paste a public Instagram photo post URL.")


def canonical_post_url(url: str) -> str:
    return f"https://www.instagram.com/p/{extract_shortcode(url)}/"


def img_index_url(post_url: str, index: int) -> str:
    return f"{canonical_post_url(post_url)}?img_index={index}"


def _url_quality_score(url: str) -> tuple[int, int]:
    query = parse_qs(urlparse(url).query)
    stp = (query.get("stp") or [""])[0]
    size = re.search(r"[_-](?:s|p)(\d+)x(\d+)", stp, re.IGNORECASE)
    if size:
        area = int(size.group(1)) * int(size.group(2))
        unconstrained = 0
    else:
        # No size cap in the CDN URL — this is the original rendition.
        area = 99_000_000
        unconstrained = 1
    return (unconstrained, area)


def _best_image_url(entry: dict) -> str | None:
    candidates: list[tuple[tuple[int, int], str]] = []
    for thumb in entry.get("thumbnails") or []:
        url = thumb.get("url")
        if not url:
            continue
        declared = int(thumb.get("width") or 0) * int(thumb.get("height") or 0)
        unconstrained, url_area = _url_quality_score(url)
        area = max(declared, url_area) if declared else url_area
        candidates.append(((unconstrained, area), url))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _entries_from_info(info: dict) -> list[dict]:
    if info.get("_type") == "playlist":
        return [entry for entry in (info.get("entries") or []) if entry]
    return [info]


def _extract_sync(url: str) -> dict:
    with YoutubeDL(YDL_OPTS) as ydl:
        return ydl.extract_info(url, download=False)


async def resolve_post(url: str) -> PostMedia:
    shortcode = extract_shortcode(url)
    post_url = canonical_post_url(url)
    try:
        info = await asyncio.to_thread(_extract_sync, post_url)
    except (DownloadError, ExtractorError) as exc:
        message = str(exc).lower()
        if "login" in message or "private" in message:
            raise InstagramError("That post is private or Instagram asked for a login.") from exc
        raise InstagramError("Could not load images from that post.") from exc
    except Exception as exc:
        raise InstagramError("Could not load images from that post.") from exc

    if not info:
        raise InstagramError("Could not load images from that post.")

    slides: list[Slide] = []
    for index, entry in enumerate(_entries_from_info(info), start=1):
        image_url = _best_image_url(entry)
        if image_url:
            slides.append(Slide(url=image_url, img_index=index))

    if not slides:
        raise InstagramError("Could not load images from that post.")

    return PostMedia(
        shortcode=str(info.get("id") or shortcode),
        slides=slides,
        caption=info.get("description"),
        title=info.get("title") or info.get("uploader"),
    )


async def download_images(slides: list[Slide]) -> list[bytes]:
    images: list[bytes] = []
    headers = {
        "User-Agent": BROWSER_UA,
        "Referer": "https://www.instagram.com/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=45.0, headers=headers) as client:
        for slide in slides:
            response = await client.get(slide.url)
            if response.status_code != 200 or not response.content:
                raise InstagramError("Could not download an image (the link may have expired). Try again.")
            images.append(enhance_image(response.content))
    return images
