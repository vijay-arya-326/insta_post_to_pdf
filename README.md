# Instagram post to PDF / YouTube videos

Local web app with two tabs:

- **Insta Post to PDF** — turn a public Instagram photo post into a PDF.
- **Youtube Videos** — download a YouTube video as the best MP4, or audio as MP3, using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

No Instagram or YouTube login. Private or login-walled posts/videos will fail. MP4 merge and MP3 conversion need **ffmpeg** on your PATH.

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

## Start automatically when the OS starts

Run `uv sync` once in this folder first. Autostart files live under `autostart/windows` and `autostart/macos`. They start the server **without** `--reload`.

### Windows

Files: `autostart/windows/`

1. Double-click `install-autostart.bat`. That adds a Startup shortcut to `start-hidden.vbs`, which launches uvicorn with no console window.
2. Sign in again and open [http://127.0.0.1:8585](http://127.0.0.1:8585).

To stop autostart, run `uninstall-autostart.bat`. To stop a running copy, end the `uvicorn`/`python` process in Task Manager (there is no window to close). Use `start-insta-post-to-pdf.bat` only if you want a visible console for debugging.

### macOS

Files: `autostart/macos/`

```bash
chmod +x autostart/macos/install-autostart.sh autostart/macos/uninstall-autostart.sh autostart/macos/start-insta-post-to-pdf.sh
./autostart/macos/install-autostart.sh
```

That writes a LaunchAgent from `com.local.insta-post-to-pdf.plist` and starts the helper script `start-insta-post-to-pdf.sh`.

To stop and remove autostart:

```bash
./autostart/macos/uninstall-autostart.sh
```

### Ubuntu

1. Create `~/.config/systemd/user/insta-post-to-pdf.service`:

```ini
[Unit]
Description=Instagram post to PDF
After=network.target

[Service]
WorkingDirectory=PROJECT_DIR
ExecStart=UV_PATH run uvicorn app:app --host 127.0.0.1 --port 8585
Restart=on-failure

[Install]
WantedBy=default.target
```

`UV_PATH` is usually `/home/YOUR_USER/.local/bin/uv`.

2. Enable it for your user session:

```bash
systemctl --user daemon-reload
systemctl --user enable --now insta-post-to-pdf.service
```

It starts when you log in. To also start it when you are not logged in:

```bash
loginctl enable-linger "$USER"
```

To stop and disable:

```bash
systemctl --user disable --now insta-post-to-pdf.service
```

## How to use

### Insta Post to PDF

1. In Instagram, open a **public photo post** and copy the link (Share → Copy link).  
   Example: `https://www.instagram.com/p/DcvziYVgesG`
2. Paste it into the URL field and enter a PDF filename.
3. Click **Preview** to load every slide (`img_index=1` through the last image). **Download PDF** stays disabled until preview succeeds.
4. Click **Download PDF**. If you change the URL, preview again first.

Each photo is one PDF page, at the original image size.

### Youtube Videos

1. Paste a YouTube watch / Shorts / `youtu.be` URL.
2. Choose **MP4 video** or **MP3 audio**.
3. For MP4, pick video quality: **Best available**, **1080p**, **720p**, or **480p**.  
   For MP3, pick bitrate: **320**, **256**, or **192 kbps**.
4. Click **Preview**, then **Download**. Download stays disabled until preview succeeds. If you change the URL, preview again first.
5. Playlist links list every video. Leave **Download all videos one by one** checked: each file finishes before the next starts. Uncheck it to save only the first video.

Install ffmpeg if the tab says it was not found (Windows: `winget install Gyan.FFmpeg`, macOS: `brew install ffmpeg`, Ubuntu: `sudo apt install ffmpeg`).

## If something goes wrong

- **Port 8585 already in use** — stop the old server (`Ctrl+C` in that terminal) and start it again.
- **Module not found / missing packages** — run `uv sync` in this folder, then start the server with `uv run` again.
- **Could not load images** — the post may be private, deleted, or a video-only post.
- **Could not download that YouTube video** — the video may be private, age-restricted, or ffmpeg may be missing.
- **Blurry PDF** — download again after a code update; the app caches a post for about 10 minutes.
