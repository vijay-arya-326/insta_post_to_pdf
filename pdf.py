from __future__ import annotations

import base64
import io

import img2pdf
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA", "P"}:
        background = Image.new("RGB", image.size, (255, 255, 255))
        converted = image.convert("RGBA")
        background.paste(converted, mask=converted.split()[-1])
        return background
    return image.convert("RGB")


def _jpeg_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    _to_rgb(image).save(
        buf,
        format="JPEG",
        quality=98,
        subsampling=0,
        optimize=True,
        dpi=(72, 72),
    )
    return buf.getvalue()


def enhance_image(raw: bytes) -> bytes:
    """Light sharpen for text slides; keep the original pixel size."""
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        im = ImageOps.exif_transpose(im)
        im = _to_rgb(im)
        im = ImageEnhance.Contrast(im).enhance(1.04)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.1, percent=115, threshold=2))
        return _jpeg_bytes(im)


def images_to_pdf(images: list[bytes]) -> bytes:
    pages: list[bytes] = []
    for raw in images:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            fmt = (im.format or "").upper()
            if fmt in {"JPEG", "JPG"} and im.mode == "RGB":
                pages.append(raw)
            else:
                pages.append(_jpeg_bytes(im))
    if not pages:
        raise ValueError("No images to put in the PDF.")
    # Screen viewing: keep each photo's aspect, do not fit to A4/Letter.
    return img2pdf.convert(pages, dpi=72)


def thumbnail_data_url(raw: bytes, max_size: int = 360) -> tuple[str, int, int]:
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        width, height = im.size
        thumb = im.copy()
        thumb.thumbnail((max_size, max_size))
        thumb = _to_rgb(thumb)
        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", quality=88, subsampling=0)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", width, height
