import os
import json
import anthropic

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def extract_study_material(transcript: str, jlpt_level: str = "N3") -> list[dict]:
    """Extract vocab, grammar, and collocations from transcript using Claude."""
    if not transcript or not transcript.strip():
        raise ValueError("Transcript is empty — nothing to extract from")

    target_levels = _get_target_levels(jlpt_level)

    prompt = f"""You are a Japanese language teacher helping an intermediate learner study for JLPT {jlpt_level} (targeting {jlpt_level} now, eventually N2).

The learner is high-intermediate: comfortable with daily conversation but has clunky grammar and gaps in vocabulary. They can understand 60-80% of native podcasts.

Analyze this Japanese podcast transcript and extract study material. Focus on items at {' and '.join(target_levels)} level.

EXTRACT THREE CATEGORIES:

1. **vocab** — Words/phrases the learner should know for {jlpt_level} and natural conversation.
   Skip basic N5/N4 words unless they're used in a non-obvious way.

2. **grammar** — Grammar patterns at {jlpt_level}+ level, especially ones that:
   - Appear in natural speech but learners tend to avoid
   - Show how natives actually construct sentences (vs textbook patterns)

3. **collocation** — Natural word combinations, set phrases, sentence patterns that sound native.
   These are the things that fix "clunky" Japanese — how words naturally pair together.

For EACH item, provide:
- "type": "vocab" | "grammar" | "collocation"
- "japanese": the word/pattern/phrase
- "reading": hiragana reading (for vocab; omit for grammar/collocations if obvious)
- "english": clear, concise meaning
- "jlpt_tag": estimated JLPT level (N1-N5)
- "context_sentence": the ACTUAL sentence from the transcript where this appeared
- "usage_note": 1-2 sentences on nuance, register, common mistakes, or when to use this

Aim for 10-20 vocab, 5-10 grammar, 5-10 collocations — quality over quantity.

Return ONLY a JSON array. No markdown, no explanation.

TRANSCRIPT:
{transcript[:12000]}"""

    message = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Clean potential markdown fencing
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}. Response preview: {text[:500]}")

    return items


def _get_target_levels(level: str) -> list[str]:
    """Return which JLPT levels to focus on given current target."""
    level_map = {
        "N5": ["N5"],
        "N4": ["N4", "N5"],
        "N3": ["N3", "N4"],
        "N2": ["N2", "N3"],
        "N1": ["N1", "N2"],
    }
    return level_map.get(level, ["N3", "N2"])
