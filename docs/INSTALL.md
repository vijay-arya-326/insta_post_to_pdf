# Installation

Everything you need to install and run the app, including starting it automatically when the OS starts.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.11+ (uv can install this if it is missing)
- [ffmpeg](https://ffmpeg.org/) on your PATH (MP4 merge, MP3 conversion)
- [deno](https://deno.com/) on your PATH (YouTube JS-challenge solver, required for every download)

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On macOS you can also use `brew install uv`.

### Install ffmpeg and deno

| OS       | Commands |
| -------- | -------- |
| macOS    | `brew install ffmpeg deno` |
| Windows  | `winget install Gyan.FFmpeg deno.land`, or get [ffmpeg](https://ffmpeg.org/download.html) and [deno](https://deno.com/) from their sites and add them to PATH |
| Ubuntu   | `sudo apt install ffmpeg` then `curl -fsSL https://deno.land/install.sh | sh` |

## Resolve dependencies

From the project folder, install the locked packages into a local `.venv`:

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

## Start the server manually

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