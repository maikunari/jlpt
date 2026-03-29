import os
import shutil
from groq import Groq
from pathlib import Path

def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio file using Groq Whisper Large v3."""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    file_size = os.path.getsize(audio_path)
    max_size = 25 * 1024 * 1024  # 25MB Groq limit

    if file_size > max_size:
        return _transcribe_chunked(audio_path, client)

    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=(Path(audio_path).name, f.read()),
            model="whisper-large-v3",
            language="ja",
            response_format="text",
        )

    return transcription


def _transcribe_chunked(audio_path: str, client: Groq) -> str:
    """Split large files and transcribe in chunks using ffmpeg."""
    import subprocess
    import tempfile

    chunk_dir = tempfile.mkdtemp()
    try:
        chunk_pattern = os.path.join(chunk_dir, "chunk_%03d.mp3")

        # Split into 10-minute chunks
        subprocess.run(
            [
                "ffmpeg", "-i", audio_path,
                "-f", "segment",
                "-segment_time", "600",
                "-c", "copy",
                chunk_pattern,
            ],
            capture_output=True, check=True,
        )

        chunks = sorted(Path(chunk_dir).glob("chunk_*.mp3"))
        transcripts = []

        for chunk in chunks:
            with open(chunk, "rb") as f:
                text = client.audio.transcriptions.create(
                    file=(chunk.name, f.read()),
                    model="whisper-large-v3",
                    language="ja",
                    response_format="text",
                )
                transcripts.append(text)

        return "\n".join(transcripts)
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)
