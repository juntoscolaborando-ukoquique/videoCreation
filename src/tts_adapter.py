"""
TTS Adapter — Text-to-Speech bridge.

Supports:
  - ``edge_tts`` (free, no API key) — default; Microsoft Neural voices via
    the open-source ``edge-tts`` package
  - ``openai`` — OpenAI TTS API (requires ``openai`` package and
    ``OPENAI_API_KEY`` environment variable)
  - ffmpeg silent-audio fallback — used automatically when all TTS methods
    fail, or when ``edge-tts`` / ``openai`` are not installed

Multi-language support via config ``language_voices``. MD5-based audio
caching in ``<project_root>/.cache/tts/`` prevents redundant re-generation of identical text.
"""

import asyncio
import concurrent.futures
import hashlib
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from src import config_loader as _default_config_loader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_voice_mappings():
    """Ensure all languages defined in schema have a default voice mapping in config.

    Raises
    ------
    RuntimeError
        If any ``Language`` value is missing from ``tts.language_voices`` in
        ``default_config.yaml``. Surfaces config gaps at startup rather than
        letting them produce silent fallbacks at generation time.
    """
    from src.schema import Language
    cfg_voices = _default_config_loader.tts().get("language_voices", {})
    missing = [lang for lang in Language if lang.value not in cfg_voices]
    if missing:
        names = ", ".join(lang.name for lang in missing)
        raise RuntimeError(
            f"Missing TTS voice mapping(s) for: {names}. "
            "Add the missing language codes to tts.language_voices in default_config.yaml."
        )


# Call explicitly at startup (e.g. from main.py) rather than on every import.
# validate_voice_mappings()  — call manually if you want the startup check.


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
    config_loader=None,
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
    config_loader:
        Optional ``ConfigLoader`` instance. Defaults to the module singleton.

    Returns
    -------
    str
        The absolute path to the generated audio file.
    """
    _cfg = config_loader or _default_config_loader
    cfg = _cfg.tts()
    if method is None:
        method = cfg.get("method", "edge_tts")

    if rate is None:
        rate = cfg.get("rate", "+0%")

    # Voice resolution: explicit > language default > config default > hardcoded
    if voice:
        resolved_voice = voice
    elif language:
        # Config language_voices is the single source of truth
        cfg_voices = cfg.get("language_voices", {})
        resolved_voice = cfg_voices.get(language)
        if resolved_voice:
            logger.info("TTS language='%s' → voice='%s'", language, resolved_voice)
        else:
            resolved_voice = cfg.get("voice", "en-US-GuyNeural")
            logger.warning("No voice mapping for language '%s' — using '%s'.", language, resolved_voice)
    else:
        resolved_voice = cfg.get("voice", "en-US-GuyNeural")

    use_cache = cfg.get("use_cache", True)
    if use_cache:
        cache_dir = Path(__file__).resolve().parent.parent / ".cache" / "tts"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Include rate in cache key to ensure changes in speaking rate are reflected
        key_data = f"{text}|{method}|{resolved_voice}|{rate}".encode("utf-8")
        file_hash = hashlib.md5(key_data).hexdigest()
        ext = Path(output_path).suffix or ".mp3"
        cache_file = cache_dir / f"{file_hash}{ext}"
        
        if cache_file.exists() and cache_file.stat().st_size > 0:
            logger.info("TTS cache hit for '%s...' voice='%s' rate='%s'.", text[:20], resolved_voice, rate)
            shutil.copy2(cache_file, output_path)
            return output_path
        elif cache_file.exists():
            logger.warning("TTS cache file is empty, regenerating: %s", cache_file)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    res = None
    success = False
    if method == "edge_tts":
        res, success = _edge_tts(text, output_path, resolved_voice, rate)
    elif method == "openai":
        res, success = _openai_tts(text, output_path, resolved_voice)
    elif method in ("azure", "fish_tts"):
        raise NotImplementedError(
            f"TTS backend '{method}' is declared in the schema but not yet implemented. "
            "Use 'edge_tts' (default, free) or 'openai' (requires OPENAI_API_KEY)."
        )
    else:
        logger.warning("TTS method '%s' not recognised — generating silent placeholder.", method)
        res = _generate_silent_audio(output_path)
        success = False  # silent fallback must not be cached

    if use_cache and success and res and Path(res).exists():
        shutil.copy2(res, cache_file)

    return res


# ---------------------------------------------------------------------------
# edge_tts backend
# ---------------------------------------------------------------------------

def _edge_tts(text: str, output_path: str, voice: str, rate: str = "+0%") -> tuple:
    """Generate speech with Microsoft Edge TTS (free, no key).

    Returns (path, success) tuple.
    """
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
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: asyncio.run(_run()))
                future.result()
        else:
            asyncio.run(_run())
        logger.info("edge_tts audio saved → %s", output_path)
        return output_path, True

    except ImportError:
        logger.warning("edge_tts package not installed — falling back to silent audio.")
        return _generate_silent_audio(output_path), False
    except Exception as exc:
        logger.error("edge_tts failed (%s) — falling back to silent audio.", exc)
        return _generate_silent_audio(output_path), False


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

def _openai_tts(text: str, output_path: str, voice: str) -> tuple:
    """Generate speech with OpenAI TTS API.

    Returns (path, success) tuple.
    """
    try:
        from openai import OpenAI
        client = OpenAI()

        valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        if voice not in valid_voices:
            logger.warning("OpenAI voice '%s' is not valid — using 'alloy'. Valid voices: %s", voice, sorted(valid_voices))
            oai_voice = "alloy"
        else:
            oai_voice = voice

        logger.info("Generating OpenAI TTS with voice='%s'", oai_voice)
        response = client.audio.speech.create(
            model="tts-1",
            voice=oai_voice,
            input=text
        )
        response.stream_to_file(output_path)
        return output_path, True
    except ImportError:
        logger.error("openai package not installed. Run 'pip install openai'. Falling back to silent audio.")
        return _generate_silent_audio(output_path), False
    except Exception as exc:
        logger.error("OpenAI TTS failed: %s — falling back to silent audio.", exc)
        return _generate_silent_audio(output_path), False
