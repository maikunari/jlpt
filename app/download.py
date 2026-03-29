import subprocess
import os
from pathlib import Path

AUDIO_DIR = Path(os.getenv("AUDIO_DIR", "data/audio"))

def download_audio(url: str, episode_id: int) -> tuple[str, str]:
    """Download audio from URL, return (audio_path, title)."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    output_template = str(AUDIO_DIR / f"episode_{episode_id}.%(ext)s")
    
    # First get the title
    result = subprocess.run(
        ["yt-dlp", "--print", "title", "--no-download", url],
        capture_output=True, text=True, timeout=30
    )
    title = result.stdout.strip() or f"Episode {episode_id}"
    
    # Download audio only
    subprocess.run(
        [
            "yt-dlp",
            "-x",  # extract audio
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_template,
            "--no-playlist",
            url,
        ],
        capture_output=True, text=True, timeout=600,
        check=True,
    )
    
    # Find the downloaded file
    audio_path = str(AUDIO_DIR / f"episode_{episode_id}.mp3")
    if not os.path.exists(audio_path):
        # yt-dlp might keep original extension
        for f in AUDIO_DIR.glob(f"episode_{episode_id}.*"):
            audio_path = str(f)
            break
    
    return audio_path, title
