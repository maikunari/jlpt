import httpx
import json

ANKI_URL = "http://127.0.0.1:8765"
DECK_NAME = "JLPT Podcast Study"
MODEL_NAME = "JLPT Podcast Card"

_deck_ready = False

async def _anki_request(action: str, **params) -> dict:
    """Send a request to AnkiConnect."""
    payload = {"action": action, "version": 6}
    if params:
        payload["params"] = params
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(ANKI_URL, json=payload, timeout=10)
        try:
            result = resp.json()
        except Exception:
            raise Exception(f"AnkiConnect returned non-JSON response (status {resp.status_code}): {resp.text[:200]}")
        if result.get("error"):
            raise Exception(f"AnkiConnect error: {result['error']}")
        return result.get("result")


async def ensure_deck_and_model():
    """Create the deck and note model if they don't exist."""
    global _deck_ready
    if _deck_ready:
        return
    # Create deck
    await _anki_request("createDeck", deck=DECK_NAME)
    
    # Check if model exists
    models = await _anki_request("modelNames")
    if MODEL_NAME not in models:
        await _anki_request(
            "createModel",
            modelName=MODEL_NAME,
            inOrderFields=["Japanese", "Reading", "English", "Type", "JLPTLevel", "ContextSentence", "UsageNote", "EpisodeTitle"],
            css="""
                .card { font-family: "Hiragino Kaku Gothic Pro", "Yu Gothic", sans-serif; 
                        font-size: 20px; text-align: center; padding: 20px; 
                        background: #1a1a2e; color: #e0e0e0; }
                .japanese { font-size: 32px; margin-bottom: 10px; color: #e94560; }
                .reading { font-size: 18px; color: #999; margin-bottom: 15px; }
                .english { font-size: 20px; margin-bottom: 15px; }
                .context { font-size: 16px; color: #aaa; margin: 15px 0; 
                           padding: 10px; border-left: 3px solid #e94560; 
                           text-align: left; background: #16213e; }
                .note { font-size: 14px; color: #888; margin-top: 10px; 
                        text-align: left; font-style: italic; }
                .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; 
                       font-size: 12px; margin: 5px 2px; }
                .tag-vocab { background: #0f3460; color: #4cc9f0; }
                .tag-grammar { background: #3d1a5c; color: #c77dff; }
                .tag-collocation { background: #1a3c2e; color: #52b788; }
                .tag-jlpt { background: #3d2e1a; color: #f4a261; }
            """,
            cardTemplates=[
                {
                    "Name": "Recognition",
                    "Front": """
                        <div class="japanese">{{Japanese}}</div>
                        {{#Reading}}<div class="reading">{{Reading}}</div>{{/Reading}}
                        <div><span class="tag tag-{{Type}}">{{Type}}</span>
                        <span class="tag tag-jlpt">{{JLPTLevel}}</span></div>
                    """,
                    "Back": """
                        <div class="japanese">{{Japanese}}</div>
                        {{#Reading}}<div class="reading">{{Reading}}</div>{{/Reading}}
                        <hr>
                        <div class="english">{{English}}</div>
                        {{#ContextSentence}}<div class="context">{{ContextSentence}}</div>{{/ContextSentence}}
                        {{#UsageNote}}<div class="note">💡 {{UsageNote}}</div>{{/UsageNote}}
                        <div><span class="tag tag-{{Type}}">{{Type}}</span>
                        <span class="tag tag-jlpt">{{JLPTLevel}}</span></div>
                        <div class="note">📻 {{EpisodeTitle}}</div>
                    """,
                },
            ],
        )
    _deck_ready = True


async def add_note(item: dict, episode_title: str = "") -> int:
    """Add a single extraction to Anki. Returns the note ID."""
    await ensure_deck_and_model()
    
    note_id = await _anki_request(
        "addNote",
        note={
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {
                "Japanese": item["japanese"],
                "Reading": item.get("reading", ""),
                "English": item["english"],
                "Type": item["type"],
                "JLPTLevel": item.get("jlpt_tag", ""),
                "ContextSentence": item.get("context_sentence", ""),
                "UsageNote": item.get("usage_note", ""),
                "EpisodeTitle": episode_title,
            },
            "options": {"allowDuplicate": False},
            "tags": [f"jlpt::{item.get('jlpt_tag', 'unknown')}", f"type::{item['type']}", "podcast"],
        },
    )
    return note_id


async def add_notes_batch(items: list[dict], episode_title: str = "") -> list[int]:
    """Add multiple extractions to Anki. Returns list of note IDs."""
    await ensure_deck_and_model()
    
    notes = []
    for item in items:
        notes.append({
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {
                "Japanese": item["japanese"],
                "Reading": item.get("reading", ""),
                "English": item["english"],
                "Type": item["type"],
                "JLPTLevel": item.get("jlpt_tag", ""),
                "ContextSentence": item.get("context_sentence", ""),
                "UsageNote": item.get("usage_note", ""),
                "EpisodeTitle": episode_title,
            },
            "options": {"allowDuplicate": False},
            "tags": [f"jlpt::{item.get('jlpt_tag', 'unknown')}", f"type::{item['type']}", "podcast"],
        })
    
    result = await _anki_request("addNotes", notes=notes)
    return result


async def check_connection() -> bool:
    """Check if AnkiConnect is running."""
    try:
        result = await _anki_request("version")
        return result is not None
    except Exception:
        return False
