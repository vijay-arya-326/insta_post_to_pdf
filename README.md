# Instagram post to PDF / YouTube videos

Local web app with two tabs:

- **Insta Post to PDF** — turn a public Instagram photo post into a PDF.
- **Youtube Videos** — download a YouTube video as the best MP4, or audio as MP3, using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

No Instagram login is needed. YouTube works signed out, or signed in by uploading a **cookies file** (for age-restricted or login-walled videos). Private or login-walled Instagram posts will fail. MP4 merge and MP3 conversion need **ffmpeg**; YouTube downloads also need **deno** for the JS-challenge solver.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.11+ (uv can install this if it is missing)
- [ffmpeg](https://ffmpeg.org/) on your PATH (MP4 merge, MP3 conversion)
- [deno](https://deno.com/) on your PATH (YouTube JS-challenge solver, required for every download)

Install uv if you do not have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On macOS you can also use `brew install uv`.

Install ffmpeg and deno (macOS):

```bash
brew install ffmpeg deno
```

Windows: `winget install Gyan.FFmpeg deno.land` — or get [ffmpeg](https://ffmpeg.org/download.html) and [deno](https://deno.com/) from their sites and put them on PATH. Ubuntu: `sudo apt install ffmpeg` and `curl -fsSL https://deno.land/install.sh | sh`.

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

Your uploaded YouTube cookies live in `uploads/cookie.txt` (git-ignored). They are reused across restarts until you click **Remove cookies** or delete the file.

## Start automatically when the OS starts (one-step install)

Each platform has a one-step installer that installs **uv** if missing, creates `.venv` and installs every package with `uv sync`, then adds the app to startup — all in one go. It starts the server **without** `--reload`.

### Windows

Files: `autostart/windows/`

1. **Double-click `install.bat`.** It checks/installs uv, runs `uv sync`, and adds a Startup shortcut to `start-hidden.vbs`, which launches uvicorn with no console window.
2. Sign in again and open [http://127.0.0.1:8585](http://127.0.0.1:8585).

To stop autostart, run `uninstall-autostart.bat`. To stop a running copy, end the `uvicorn`/`python` process in Task Manager (there is no window to close). Use `start-insta-post-to-pdf.bat` only if you want a visible console for debugging.

### macOS

Files: `autostart/macos/`

```bash
chmod +x autostart/macos/install.sh
./autostart/macos/install.sh
```

It checks/installs uv, runs `uv sync`, and writes a LaunchAgent from `com.local.insta-post-to-pdf.plist` that starts the helper script `start-insta-post-to-pdf.sh`.

To stop and remove autostart:

```bash
./autostart/macos/uninstall-autostart.sh
```

### Ubuntu

Files: `autostart/ubuntu/`

```bash
chmod +x autostart/ubuntu/install.sh
./autostart/ubuntu/install.sh
```

It checks/installs uv, runs `uv sync`, and creates `~/.config/systemd/user/insta-post-to-pdf.service` pointing at this project, then enables and starts it for your user session.

To also start when you are not logged in:

```bash
loginctl enable-linger "$USER"
```

To stop and remove autostart:

```bash
./autostart/ubuntu/uninstall.sh
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
5. Playlist links list every video. Leave **Save all videos one by one** checked: each file is written into your **Videos** folder (macOS: **Movies**) in a folder named after the playlist. A progress bar shows the current step. Uncheck it to download only the first video in the browser.

#### Signing in with cookies (recommended for logged-in downloads)

Some videos (age-restricted, unlisted-but-sharing, or login-walled) only download when YouTube knows your signed-in session. The app will often say **"Please sign in"** for these. Upload your YouTube cookies to fix this:

1. Export your YouTube cookies from your browser as a Netscape-format `.txt` file. Easiest option: install the **"Get cookies.txt LOCALLY"** browser extension (Chrome/Firefox) and export from youtube.com. For other methods, see the [yt-dlp cookie guide](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).
2. In the app, open a page that says **Cookie file**, pick the exported `.txt` file, and it is uploaded immediately.
3. A green **"YouTube session ready"** box appears. It shows who you are logged in as when an email is embedded in the cookies ("You will be logged in as ..."), otherwise a cookie count. Click **Show cookie content** to inspect the uploaded file (collapsed by default). Click **Remove cookies** to delete the file and go back to signed-out downloads.

The uploaded file is saved as `uploads/cookie.txt` in the project folder (overwriting any previous one) and is used for every download until you remove it. Re-uploading a fresh export regularly keeps your session working, since YouTube cookies expire.

No browser export? The **YouTube cookies** dropdown lets you pick a browser that is already logged in to YouTube (`cookies-from-browser`), or you can choose **Cookie file** to upload.

Install ffmpeg if the tab says it was not found, and deno if the JS-challenge solver reports it is missing (commands above).

## If something goes wrong

- **Port 8585 already in use** — stop the old server (`Ctrl+C` in that terminal) and start it again.
- **Module not found / missing packages** — run `uv sync` in this folder, then start the server with `uv run` again.
- **ffmpeg / deno not found errors** — make sure both are installed and on your PATH, then restart the server.
- **"Please sign in" when downloading** — YouTube rejected the request. Either this is a login-walled video (upload your cookies, see above), your uploaded `uploads/cookie.txt` has expired (re-export and re-upload), or the export does not contain a valid session (`__Secure-3PSID`, `LOGIN_INFO`, etc.). Use the "Get cookies.txt LOCALLY" extension for export.
- **Could not load images** — the post may be private, deleted, or a video-only post.
- **Could not download that YouTube video** — the video may be private, age-restricted, ffmpeg may be missing, or cookies may be required (see above).
- **Blurry PDF** — download again after a code update; the app caches a post for about 10 minutes.
