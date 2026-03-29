import subprocess
import os
from pathlib import Path

AUDIO_DIR = Path(os.getenv("AUDIO_DIR", "data/audio"))

# Browser to pull cookies from — Safari works on macOS without extra setup.
# Change to "chrome" or "firefox" if preferred.
COOKIES_BROWSER = os.getenv("COOKIES_BROWSER", "chrome")

def _yt_dlp_args(extra: list) -> list:
    """Base yt-dlp args, always including browser cookies to avoid 403s."""
    return ["yt-dlp", "--cookies-from-browser", COOKIES_BROWSER] + extra

def download_audio(url: str, episode_id: int) -> tuple[str, str]:
    """Download audio from URL, return (audio_path, title)."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    output_template = str(AUDIO_DIR / f"episode_{episode_id}.%(ext)s")

    # First get the title
    result = subprocess.run(
        _yt_dlp_args(["--print", "title", "--no-download", url]),
        capture_output=True, text=True, timeout=30
    )
    title = result.stdout.strip() or f"Episode {episode_id}"

    # Download audio only
    result = subprocess.run(
        _yt_dlp_args([
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_template,
            "--no-playlist",
            url,
        ]),
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"yt-dlp failed: {stderr[-800:]}")

    # Find the downloaded file
    audio_path = str(AUDIO_DIR / f"episode_{episode_id}.mp3")
    if not os.path.exists(audio_path):
        for f in AUDIO_DIR.glob(f"episode_{episode_id}.*"):
            audio_path = str(f)
            break

    return audio_path, title
