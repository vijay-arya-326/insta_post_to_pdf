# Troubleshooting

Common errors and how to fix them.

- **Port 8585 already in use** — stop the old server (`Ctrl+C` in that terminal) and start it again.
- **Module not found / missing packages** — run `uv sync` in this folder, then start the server with `uv run` again.
- **ffmpeg / deno not found errors** — make sure both are installed and on your PATH, then restart the server. See [Installation](INSTALL.md).
- **"Please sign in" when downloading** — YouTube rejected the request. Either this is a login-walled video (upload your cookies, see [YouTube cookies](COOKIES.md)), your uploaded `uploads/cookie.txt` has expired (re-export and re-upload), or the export does not contain a valid session (`__Secure-3PSID`, `LOGIN_INFO`, etc.). Use the "Get cookies.txt LOCALLY" extension for export.
- **Could not load images** — the post may be private, deleted, or a video-only post.
- **Could not download that YouTube video** — the video may be private, age-restricted, ffmpeg may be missing, or cookies may be required. See [YouTube cookies](COOKIES.md).
- **Blurry PDF** — download again after a code update; the app caches a post for about 10 minutes.