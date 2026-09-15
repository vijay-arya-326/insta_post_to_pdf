# YouTube cookies

Signing in makes downloads work for videos that need your account session.

## Why cookies?

Some videos (age-restricted, unlisted-but-sharing, or login-walled) only download when YouTube knows your signed-in session. Without cookies the app will often say **"Please sign in"** for these.

## Signing in with cookies

1. Export your YouTube cookies from your browser as a Netscape-format `.txt` file. Easiest option: install the **"Get cookies.txt LOCALLY"** browser extension (Chrome/Firefox) and export from youtube.com. For other methods, see the [yt-dlp cookie guide](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).
2. In the app, open a page that says **Cookie file**, pick the exported `.txt` file, and it is uploaded immediately.
3. A green **"YouTube session ready"** box appears. It shows who you are logged in as when an email is embedded in the cookies ("You will be logged in as ..."), otherwise a cookie count. Click **Show cookie content** to inspect the uploaded file (collapsed by default). Click **Remove cookies** to delete the file and go back to signed-out downloads.

## How the file is stored

The uploaded file is saved as `uploads/cookie.txt` in the project folder (overwriting any previous one) and is used for every download until you remove it. It is git-ignored and reused across restarts.

YouTube cookies expire, so **re-upload a fresh export regularly** to keep your session working. If downloads start failing with "Please sign in", your cookie file has likely expired — remove and re-export it.

## No browser export?

The **YouTube cookies** dropdown lets you pick a browser that is already logged in to YouTube (`cookies-from-browser`), or you can choose **Cookie file** to upload instead.