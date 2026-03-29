# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

JLPT Podcast Study App — extracts Japanese vocabulary, grammar, and collocations from podcast/YouTube audio using AI (Groq transcription + Claude extraction), with spaced repetition scheduling and Anki flashcard sync.

## Commands

```bash
# Activate virtualenv and run dev server
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

No tests, linter, or build step configured. Prerequisites: Python 3.11+, yt-dlp, ffmpeg, Anki + AnkiConnect plugin.

## Architecture

**Processing pipeline** (runs as FastAPI background task):
URL → `download.py` (yt-dlp → MP3) → `transcribe.py` (Groq Whisper, auto-chunks >25MB) → `extract.py` (Claude, truncates transcript to 12k chars) → SQLite

**Key modules in `app/`:**
- `database.py` — SQLite with WAL mode, all CRUD operations, SRS re-listen scheduling (intervals: 1, 3, 7, 14, 30 days then monthly)
- `download.py` — yt-dlp wrapper, returns (audio_path, title)
- `transcribe.py` — Groq Whisper Large v3, splits files >25MB into 10-min chunks via ffmpeg
- `extract.py` — Claude Sonnet 4 with 4096 token limit, returns structured JSON (type/japanese/reading/english/jlpt_tag/context_sentence/usage_note)
- `anki.py` — AnkiConnect HTTP integration (deck: "JLPT Podcast Study", model: "JLPT Podcast Card")

**Frontend:** `static/index.html` — single-file vanilla JS SPA. Polls API every 5s for episode status, 30s for re-listens. Dark theme with Noto Sans JP.

**Database:** SQLite at `data/jlpt_study.db`. Tables: `episodes`, `extractions`, `listens`, `relisten_schedule`. All queries use parameterized `?` placeholders.

**Environment variables:** `GROQ_API_KEY`, `ANTHROPIC_API_KEY` (required). `DB_PATH`, `AUDIO_DIR` (optional, default to `data/`).

## API Routes (main.py)

All routes prefixed `/api/`. Key patterns:
- `POST /api/episodes` kicks off background processing
- Episode detail endpoint returns extractions + listen history joined
- Anki push endpoints use `httpx.AsyncClient` to talk to AnkiConnect on localhost
- SRS endpoints: `/api/relistens/due`, `/api/relistens/upcoming`
