# Instagram post to PDF

Local web app that turns a **public Instagram photo post** into a PDF. Paste a post link, preview every carousel slide, then download one page per photo. No Instagram login.

Image posts only (including carousels). Private or login-walled posts will fail.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.11+ (uv can install this if it is missing)

Install uv if you do not have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On macOS you can also use `brew install uv`.

## Resolve dependencies

From this project folder, install the locked packages into a local `.venv`:

```bash
uv sync
```

That reads `pyproject.toml` (and `uv.lock` if present), creates `.venv`, and installs FastAPI, yt-dlp, Pillow, and the rest.

Run `uv sync` again whenever dependencies change, after a fresh clone, or if imports fail.

To refresh the lock file from `pyproject.toml`:

```bash
uv lock
uv sync
```

## Start the server

```bash
uv run uvicorn app:app --reload --port 8585
```

Leave that terminal open. Open the app in your browser:

[http://127.0.0.1:8585](http://127.0.0.1:8585)

`uv run` uses the `.venv` from `uv sync`, so you do not need to activate the environment yourself.

## How to use

1. In Instagram, open a **public photo post** and copy the link (Share → Copy link).  
   Example: `https://www.instagram.com/p/DcvziYVgesG`
2. Paste it into the URL field.
3. Click **Preview** to load every slide (`img_index=1` through the last image).
4. Click **Download PDF**. The file is named from the post **title** (or the start of the caption if there is no title).

Each photo is one PDF page, at the original image size.

## If something goes wrong

- **Port 8585 already in use** — stop the old server (`Ctrl+C` in that terminal) and start it again.
- **Module not found / missing packages** — run `uv sync` in this folder, then start the server with `uv run` again.
- **Could not load images** — the post may be private, deleted, or a video-only post.
- **Blurry PDF** — download again after a code update; the app caches a post for about 10 minutes.
