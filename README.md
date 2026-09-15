# Instagram post to PDF / YouTube videos

Local web app with two tabs:

- **Insta Post to PDF** — turn a public Instagram photo post into a PDF.
- **Youtube Videos** — download a YouTube video as the best MP4, or audio as MP3, using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

No Instagram login is needed. YouTube works signed out, or signed in by uploading a **cookies file** for age-restricted or login-walled videos. MP4 merge and MP3 conversion need **ffmpeg**; YouTube downloads also need **deno** for the JS-challenge solver.

## Quick start

1. Install [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS: `brew install uv`). For ffmpeg/deno and platform-specific commands, see [Installation](docs/INSTALL.md).
2. From this folder, create the `.venv` and install every package:

   ```bash
   uv sync
   ```

3. Start the server:

   ```bash
   uv run uvicorn app:app --reload --port 8585
   ```

4. Open [http://127.0.0.1:8585](http://127.0.0.1:8585).

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

## More guides

- **[Installation & autostart](docs/INSTALL.md)** — requirements, dependencies, manual start, and one-step installers for Windows, macOS, and Ubuntu.
- **[YouTube cookies](docs/COOKIES.md)** — signing in for logged-in downloads and keeping the session fresh.
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** — common errors and fixes.