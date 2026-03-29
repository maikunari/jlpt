import asyncio
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from app.database import (
    init_db, create_episode, update_episode, get_episode, get_all_episodes, delete_episode,
    save_extractions, get_extractions, update_extraction_anki_id, delete_extraction,
    clear_extractions, record_listen, get_listens, get_due_relistens, get_upcoming_relistens,
    complete_relisten,
)
from app.download import download_audio
from app.transcribe import transcribe_audio
from app.extract import extract_study_material
from app import anki

app = FastAPI(title="JLPT Podcast Study")

# --- Startup ---
@app.on_event("startup")
def startup():
    init_db()

# --- Models ---
class EpisodeCreate(BaseModel):
    url: str
    jlpt_level: str = "N3"

class ListenCreate(BaseModel):
    notes: Optional[str] = None

class ExtractionIds(BaseModel):
    extraction_ids: list[int]

# --- Background processing pipeline ---
def process_episode(episode_id: int, url: str, jlpt_level: str):
    """Full pipeline: download → transcribe → extract."""
    try:
        update_episode(episode_id, status="downloading")
        audio_path, title = download_audio(url, episode_id)
        update_episode(episode_id, audio_path=audio_path, title=title, status="transcribing")
        
        transcript = transcribe_audio(audio_path)
        update_episode(episode_id, transcript=transcript, status="extracting")
        
        items = extract_study_material(transcript, jlpt_level)
        save_extractions(episode_id, items)
        update_episode(episode_id, status="ready")
        
    except Exception as e:
        update_episode(episode_id, status=f"error: {str(e)[:200]}")
        raise

# --- API Routes ---

@app.post("/api/episodes")
async def create_new_episode(data: EpisodeCreate, bg: BackgroundTasks):
    """Submit a new podcast/youtube URL for processing."""
    parsed = urlparse(data.url)
    if parsed.scheme not in ('http', 'https'):
        raise HTTPException(400, "URL must start with http:// or https://")
    eid = create_episode(data.url, jlpt_level=data.jlpt_level)
    bg.add_task(process_episode, eid, data.url, data.jlpt_level)
    return {"id": eid, "status": "processing"}

@app.get("/api/episodes")
async def list_episodes():
    return get_all_episodes()

@app.get("/api/episodes/{eid}")
async def get_episode_detail(eid: int):
    ep = get_episode(eid)
    if not ep:
        raise HTTPException(404, "Episode not found")
    ep["extractions"] = get_extractions(eid)
    ep["listens"] = get_listens(eid)
    return ep

@app.get("/api/episodes/{eid}/extractions")
async def get_episode_extractions(eid: int):
    return get_extractions(eid)

@app.post("/api/episodes/{eid}/retry")
async def retry_episode(eid: int, bg: BackgroundTasks):
    """Re-run the full processing pipeline for a failed episode."""
    ep = get_episode(eid)
    if not ep:
        raise HTTPException(404, "Episode not found")
    if not ep["status"].startswith("error"):
        raise HTTPException(400, "Episode is not in an error state")
    clear_extractions(eid)
    update_episode(eid, status="pending", audio_path=None, transcript=None)
    bg.add_task(process_episode, eid, ep["url"], ep["jlpt_level"])
    return {"id": eid, "status": "processing"}

@app.delete("/api/episodes/{eid}")
async def remove_episode(eid: int):
    ep = get_episode(eid)
    if not ep:
        raise HTTPException(404, "Episode not found")
    delete_episode(eid)
    return {"ok": True}

@app.delete("/api/extractions/{extraction_id}")
async def remove_extraction(extraction_id: int):
    delete_extraction(extraction_id)
    return {"ok": True}

@app.post("/api/episodes/{eid}/push-to-anki")
async def push_to_anki(eid: int, data: ExtractionIds):
    """Push selected extractions to Anki."""
    connected = await anki.check_connection()
    if not connected:
        raise HTTPException(503, "Anki not running or AnkiConnect not installed. Open Anki first.")
    
    ep = get_episode(eid)
    extractions = get_extractions(eid)
    selected = [e for e in extractions if e["id"] in data.extraction_ids]
    
    if not selected:
        raise HTTPException(400, "No extractions selected")
    
    note_ids = await anki.add_notes_batch(selected, episode_title=ep.get("title", ""))
    
    pushed = 0
    for ext, note_id in zip(selected, note_ids):
        if note_id:
            update_extraction_anki_id(ext["id"], note_id)
            pushed += 1
    
    return {"pushed": pushed, "duplicates": len(selected) - pushed}

@app.post("/api/episodes/{eid}/push-all-to-anki")
async def push_all_to_anki(eid: int):
    """Push all extractions for an episode to Anki."""
    connected = await anki.check_connection()
    if not connected:
        raise HTTPException(503, "Anki not running or AnkiConnect not installed.")
    
    ep = get_episode(eid)
    extractions = get_extractions(eid)
    unpushed = [e for e in extractions if not e.get("anki_note_id")]
    
    if not unpushed:
        return {"pushed": 0, "message": "All already in Anki"}
    
    note_ids = await anki.add_notes_batch(unpushed, episode_title=ep.get("title", ""))
    
    pushed = 0
    for ext, note_id in zip(unpushed, note_ids):
        if note_id:
            update_extraction_anki_id(ext["id"], note_id)
            pushed += 1
    
    return {"pushed": pushed, "duplicates": len(unpushed) - pushed}

@app.post("/api/episodes/{eid}/listen")
async def mark_listen(eid: int, data: ListenCreate = ListenCreate()):
    listen_id = record_listen(eid, data.notes)
    return {"listen_id": listen_id}

@app.get("/api/relistens/due")
async def due_relistens():
    return get_due_relistens()

@app.get("/api/relistens/upcoming")
async def upcoming_relistens(days: int = 7):
    return get_upcoming_relistens(days)

@app.post("/api/relistens/{schedule_id}/complete")
async def mark_relisten_complete(schedule_id: int):
    complete_relisten(schedule_id)
    return {"ok": True}

@app.get("/api/anki/status")
async def anki_status():
    connected = await anki.check_connection()
    return {"connected": connected}

# --- Serve frontend ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")
