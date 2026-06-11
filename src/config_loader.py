"""
Config loader — reads config/default_config.yaml and exposes typed settings.

Design
------
The core is ``ConfigLoader``, an instanciable class that holds its own cache
and lock.  Each instance is independent, so parallel VideoOrchestrator runs or
test suites can use separate loaders without shared state.

The module-level convenience functions (``load``, ``tts``, ``video``, …) use a
default ``ConfigLoader`` that reads from the standard project path.  This keeps
full backward compatibility: existing call sites work unchanged.

To avoid stale config in batch or parallel-test scenarios, pass a fresh
``ConfigLoader`` instance to ``VideoOrchestrator`` instead of relying on the
module default.
"""

import threading
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "default_config.yaml"
)


class ConfigLoader:
    """Isolated config loader with its own cache and lock.

    Parameters
    ----------
    config_path:
        Path to the YAML config file.  Defaults to
        ``config/default_config.yaml`` at the project root.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        """Return the parsed config dict (cached after first load)."""
        with self._lock:
            if not self._cache:
                try:
                    with open(self._path, "r") as f:
                        data = yaml.safe_load(f)
                        if data:
                            self._cache.update(data)
                except FileNotFoundError:
                    raise RuntimeError(
                        f"VideoCreation config not found: {self._path}\n"
                        "Ensure 'config/default_config.yaml' exists at the project root."
                    ) from None
            return dict(self._cache)

    def reload(self) -> Dict[str, Any]:
        """Discard cache and re-read the file from disk."""
        with self._lock:
            self._cache.clear()
        return self.load()

    def clear_cache(self) -> None:
        """Discard cache without reloading.  Useful in tests."""
        with self._lock:
            self._cache.clear()

    # ------------------------------------------------------------------
    # Typed section accessors
    # ------------------------------------------------------------------

    def tts(self) -> Dict[str, Any]:
        return self.load().get("tts", {})

    def image(self) -> Dict[str, Any]:
        return self.load().get("image", {})

    def video(self) -> Dict[str, Any]:
        return self.load().get("video", {})

    def subtitles(self) -> Dict[str, Any]:
        return self.load().get("subtitles", {})

    def cloudflare(self) -> Dict[str, Any]:
        return self.load().get("cloudflare", {})


# ---------------------------------------------------------------------------
# Module-level default instance + backward-compatible free functions
# ---------------------------------------------------------------------------

_default_loader = ConfigLoader()


def load() -> Dict[str, Any]:
    return _default_loader.load()


def _clear_cache() -> None:
    """Clear the default loader's cache.  For use in tests only."""
    _default_loader.clear_cache()


def tts() -> Dict[str, Any]:
    return _default_loader.tts()


def image() -> Dict[str, Any]:
    return _default_loader.image()


def video() -> Dict[str, Any]:
    return _default_loader.video()


def subtitles() -> Dict[str, Any]:
    return _default_loader.subtitles()


def cloudflare() -> Dict[str, Any]:
    return _default_loader.cloudflare()
