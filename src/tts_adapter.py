"""
TTS Adapter — Text-to-Speech bridge.

Supports:
  - ``edge_tts`` (free, no API key) — default; Microsoft Neural voices via
    the open-source ``edge-tts`` package
  - ``openai`` — OpenAI TTS API (requires ``openai`` package and
    ``OPENAI_API_KEY`` environment variable)
  - ffmpeg silent-audio fallback — used automatically when all TTS methods
    fail, or when ``edge-tts`` / ``openai`` are not installed

Multi-language support via ``LANGUAGE_VOICES`` mapping. MD5-based audio
caching in ``.cache/tts/`` prevents redundant re-generation of identical text.
"""

import asyncio
import concurrent.futures
import hashlib
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from src import config_loader
from src.schema import Language

logger = logging.getLogger(__name__)

# Default edge_tts voice per language code.
# Full list: https://speech.microsoft.com/portal/voicegallery
LANGUAGE_VOICES: dict = {
    Language.ENGLISH.value: "en-US-GuyNeural",
    Language.SPANISH.value: "es-AR-TomasNeural",   # Rioplatense Spanish (Argentina)
    Language.CHINESE.value: "zh-CN-YunxiNeural",
    Language.FRENCH.value: "fr-FR-HenriNeural",
    Language.GERMAN.value: "de-DE-ConradNeural",
    Language.PORTUGUESE.value: "pt-BR-AntonioNeural",
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_voice_mappings():
    """Ensure all languages defined in schema have a default voice mapping."""
    for lang in Language:
        if lang.value not in LANGUAGE_VOICES:
            logger.error("Missing TTS voice mapping for language: %s", lang.name)
            # We don't raise here to avoid breaking at startup, but it will log
            # an error that should be caught during development/CI.

# Validate on module import
validate_voice_mappings()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_speech(
    text: str,
    output_path: str,
    voice: Optional[str] = None,
    language: Optional[str] = None,
    method: Optional[str] = None,
    rate: Optional[str] = None,
) -> str:
    """Convert *text* to an audio file at *output_path*.

    Parameters
    ----------
    text:
        The text to speak.
    output_path:
        Destination file path (.wav or .mp3).
    voice:
        Explicit TTS voice identifier. If provided, takes precedence over
        *language* and the config default.
    language:
        BCP-47 language code (e.g. ``"en"``, ``"es"``). Used to pick the
        default voice when *voice* is not provided. Falls back to the config
        ``tts.voice`` value, then ``"en-US-GuyNeural"``.
    method:
        TTS backend to use. Defaults to config value (edge_tts).
    rate:
        Speaking rate (e.g. "+0%", "-10%"). Overrides config default.

    Returns
    -------
    str
        The absolute path to the generated audio file.
    """
    cfg = config_loader.tts()
    if method is None:
        method = cfg.get("method", "edge_tts")

    if rate is None:
        rate = cfg.get("rate", "+0%")

    # Voice resolution: explicit > language default > config default > hardcoded
    if voice:
        resolved_voice = voice
    elif language:
        # Config language_voices override takes precedence over the hardcoded map
        cfg_voices = cfg.get("language_voices", {})
        resolved_voice = cfg_voices.get(language) or LANGUAGE_VOICES.get(language)
        if resolved_voice:
            logger.info("TTS language='%s' → voice='%s'", language, resolved_voice)
        else:
            resolved_voice = cfg.get("voice", "en-US-GuyNeural")
            logger.warning("No voice mapping for language '%s' — using '%s'.", language, resolved_voice)
    else:
        resolved_voice = cfg.get("voice", "en-US-GuyNeural")

    use_cache = cfg.get("use_cache", True)
    if use_cache:
        cache_dir = Path(".cache/tts")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Include rate in cache key to ensure changes in speaking rate are reflected
        key_data = f"{text}|{method}|{resolved_voice}|{rate}".encode("utf-8")
        file_hash = hashlib.md5(key_data).hexdigest()
        ext = Path(output_path).suffix or ".mp3"
        cache_file = cache_dir / f"{file_hash}{ext}"
        
        if cache_file.exists():
            logger.info("TTS cache hit for '%s...' voice='%s' rate='%s'.", text[:20], resolved_voice, rate)
            shutil.copy2(cache_file, output_path)
            return output_path

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    res = None
    if method == "edge_tts":
        res = _edge_tts(text, output_path, resolved_voice, rate)
    elif method == "openai":
        res = _openai_tts(text, output_path, resolved_voice)
    elif method in ("azure", "fish_tts"):
        raise NotImplementedError(
            f"TTS backend '{method}' is declared in the schema but not yet implemented. "
            "Use 'edge_tts' (default, free) or 'openai' (requires OPENAI_API_KEY)."
        )
    else:
        logger.warning("TTS method '%s' not recognised — generating silent placeholder.", method)
        res = _generate_silent_audio(output_path)

    if use_cache and res and Path(res).exists():
        shutil.copy2(res, cache_file)

    return res


# ---------------------------------------------------------------------------
# edge_tts backend
# ---------------------------------------------------------------------------

def _edge_tts(text: str, output_path: str, voice: str, rate: str = "+0%") -> str:
    """Generate speech with Microsoft Edge TTS (free, no key)."""
    try:
        import edge_tts as edge_tts_module  # type: ignore[import-untyped]

        async def _run():
            communicate = edge_tts_module.Communicate(text, voice, rate=rate)
            await communicate.save(output_path)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # Already inside an event loop (e.g. Streamlit).
            # Run the coroutine in a separate thread with its own loop.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                # Use a lambda to ensure the coroutine is created inside the worker thread
                future = pool.submit(lambda: asyncio.run(_run()))
                future.result()
        else:
            asyncio.run(_run())
        logger.info("edge_tts audio saved → %s", output_path)
        return output_path

    except ImportError:
        logger.warning("edge_tts package not installed — falling back to silent audio.")
        return _generate_silent_audio(output_path)
    except Exception as exc:
        logger.error("edge_tts failed (%s) — falling back to silent audio.", exc)
        return _generate_silent_audio(output_path)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _generate_silent_audio(output_path: str, duration_s: float = 3.0) -> str:
    """Create a short silent audio file via ffmpeg (always available on this system)."""
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(duration_s), "-q:a", "9", "-acodec", "libmp3lame",
            output_path,
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to generate silent audio (exit {result.returncode}): "
            f"{result.stderr.decode()}"
        )
    logger.info("Silent audio placeholder saved → %s", output_path)
    return output_path

# ---------------------------------------------------------------------------
# openai backend
# ---------------------------------------------------------------------------

def _openai_tts(text: str, output_path: str, voice: str) -> str:
    """Generate speech with OpenAI TTS API."""
    try:
        from openai import OpenAI
        client = OpenAI()
        
        valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        oai_voice = voice if voice in valid_voices else "alloy"
        
        logger.info("Generating OpenAI TTS with voice='%s'", oai_voice)
        response = client.audio.speech.create(
            model="tts-1",
            voice=oai_voice,
            input=text
        )
        response.stream_to_file(output_path)
        return output_path
    except ImportError:
        logger.error("openai package not installed. Run 'pip install openai'. Falling back to silent audio.")
        return _generate_silent_audio(output_path)
    except Exception as exc:
        logger.error("OpenAI TTS failed: %s — falling back to silent audio.", exc)
        return _generate_silent_audio(output_path)
