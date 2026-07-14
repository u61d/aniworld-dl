# AniDL

A command-line tool for browsing and downloading anime/series from aniworld.to
and s.to, with an optional license-key gate (via KeyAuth) for controlled
distribution.

> **Personal/research project.** aniworld.to and s.to host content that in
> most cases isn't licensed by the underlying rights holders. Downloading
> from them may carry copyright-law exposure depending on your jurisdiction
> (this matters especially if you distribute the tool to others, not just
> when running it yourself). Use accordingly.

## Requirements

- Python 3.10+
- `ffmpeg` on your PATH (used by `yt-dlp` for muxing/remuxing)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Running

```bash
python anidlkey.py
```

On first run you'll be asked for a KeyAuth license key. Set `auto_login` in
`settings.json` to skip re-entering it on future runs (stored locally in
`auth_data.json`, which is gitignored).

## Configuration

App preferences live in `settings.json` (download folder, quality, theme,
etc.) — see the in-app settings menu for the full list, including a
`Privacy` section.

### License-abuse webhook (optional)

The app can optionally send a small login notification (username, the IP
KeyAuth already records for the account, hostname, OS, login time) to a
Discord webhook, to help spot a license key being shared/reused somewhere
unexpected. It is **off unless a webhook is configured**, and can also be
turned off explicitly via the `license_telemetry` setting.

To configure it, do **one** of:

- Set the `ANIDL_WEBHOOK_URL` environment variable, or
- Copy `secrets.json.example` to `secrets.json` and fill in `webhook_url`

`secrets.json` is gitignored — never commit a real webhook URL to source
control. A webhook URL committed to a public repo is effectively public and
can be spammed by anyone who finds it.

This notification only fires on manual license-key entry, not on
auto-login, and the app prints a one-line notice to the console whenever it
sends one.

## Building a standalone executable (optional)

```bash
pip install -r requirements-build.txt
python build_exe.py
```

Produces `dist/ShadowStream` (or `.exe` on Windows) via PyInstaller. Build
artifacts (`build/`, `dist/`, `*.spec`) are gitignored and shouldn't be
committed — they're large, platform-specific, and reproducible from source.

## Project layout

- `anidlkey.py` — main CLI entry point (scraping UI, license login flow)
- `dl.py` — episode/stream extraction and download engine
- `mal.py` — MyAnimeList (Jikan API) metadata lookups
- `keyauth.py` — KeyAuth licensing client
- `settings.py` / `settings.json` — user preferences
- `build_exe.py` — PyInstaller packaging script
