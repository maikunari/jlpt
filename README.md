# JLPT Podcast Study

Personal app for extracting Japanese study material from podcasts.

**Flow:** Paste URL → download → transcribe (Groq Whisper) → extract vocab/grammar/collocations (Claude) → push to Anki → track listens → spaced re-listen reminders

## Setup

### Prerequisites
- Python 3.11+ (required — 3.9/3.10 use LibreSSL which breaks yt-dlp downloads)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed (`brew install yt-dlp`)
- ffmpeg installed (`brew install ffmpeg`)
- [Anki](https://apps.ankiweb.net/) with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) plugin
- Groq API key (free tier works: https://console.groq.com)
- Anthropic API key

### Install

```bash
cd jlpt
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and fill in your API keys
cp .env.example .env
# Edit .env with GROQ_API_KEY and ANTHROPIC_API_KEY
```

### Run

```bash
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000

> **Note:** Use `python -m uvicorn` (not `uvicorn` directly) to ensure the venv's Python is used. The app loads `.env` automatically — no need to `source .env`.

### Updating yt-dlp

YouTube breaks yt-dlp regularly. If downloads fail, update it:

```bash
pip install -U yt-dlp
```

### Access from iPhone via Tailscale

1. Install Tailscale on Mac and iPhone
2. Run the app on Mac with `--host 0.0.0.0`
3. Access via your Mac's Tailscale IP: `http://100.x.x.x:8000`

## Usage

1. **Open Anki** (must be running for AnkiConnect)
2. Paste a YouTube or podcast URL, select your JLPT level
3. Wait for processing (download → transcribe → extract) — takes 1-3 min
4. Review extractions — remove irrelevant ones, keep what you want
5. Push to Anki (selected or all)
6. Study the flashcards in Anki
7. Listen to the episode, click "Mark listened"
8. App will schedule re-listens at: 1, 3, 7, 14, 30 days
9. Due re-listens appear in the banner at the top

## Anki Card Model

Creates a deck called "JLPT Podcast Study" with cards showing:
- **Front:** Japanese + reading + type/level tags
- **Back:** English meaning, context sentence from the episode, usage note

Cards are tagged with JLPT level, type (vocab/grammar/collocation), and "podcast".

## Notes

- Groq Whisper has a 25MB file limit; larger files are auto-chunked
- Claude extraction is limited to first ~12k chars of transcript to stay within token limits
- The re-listen SRS intervals are: 1 → 3 → 7 → 14 → 30 days, then monthly
- Data stored in `data/jlpt_study.db` (SQLite)
- Audio files stored in `data/audio/`
