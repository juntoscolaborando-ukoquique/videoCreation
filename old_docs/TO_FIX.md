# TO_FIX — Remaining Architecture Work

All 11 original bug fixes are done. All 7 structural steps and all 5 unordered correctness fixes are now complete (69 unit tests + 1 integration test passing).

Run `python -m pytest tests/ -q` after each step.

---

## Ordering rationale

1. **`tts_voice` per-video** — unblocks a real user need that already caused a silent config failure. Small schema change, contained, and makes the codebase more honest before structural work begins.
2. **`PipelineResult` dataclass** — zero-risk ergonomic win. Defines a typed return contract that the rest of the refactors will depend on.
3. **Integration test** — the `_ProgressLogger` crash proved the mock-only suite misses real regressions. Safety net goes in *before* any structural work that touches multiple files.
4. **Full DI for adapters** — large surface area, needs the integration test in place first. Fixes the misleading `config_loader` parameter on `VideoOrchestrator`.
5. **Split `image_adapter.py`** — do *after* DI so the new provider modules get the injected config from day one, not the singleton. File is already at the size where it's painful to maintain.
6. **Consolidate subtitle files** — correct cleanup, lower urgency. No user-visible impact.
7. **Deprecate `LANGUAGE_VOICES`** — depends on `tts_voice` (step 1) being stable for a while before removing the fallback. Touches tests heavily, save for last.

---

## Step 1 — [x] Add `tts_voice: Optional[str]` to `VideoConfiguration`

Done. `tts_voice` field added to `VideoConfiguration`. Orchestrator passes it through. Config files restored.

---

## Step 2 — [x] Add `PipelineResult` typed dataclass to replace `Dict[str, Any]`

Done. `PipelineResult` dataclass in `src/schema.py`. All call sites updated to attribute access.

---

## Step 3 — [x] Add integration test for `_local_moviepy_assemble`

Done. `tests/test_integration.py` with `@pytest.mark.integration`. `pytest.ini` registers the marker.

Default CI run: `pytest -m "not integration"`. Manual check: `pytest tests/test_integration.py -v`.

---

## Step 4 — [x] Thread `ConfigLoader` through adapter calls (full DI fix)

Done. All four adapters (`tts_adapter`, `image_adapter`, `subtitle_adapter`, `assembler_adapter`) accept an optional `config_loader` parameter defaulting to the module singleton. Orchestrator passes `self._config` at every call site. Docstring warning removed.

---

## Step 5 — [x] Split `image_adapter.py` into `src/image_providers/` package

Done. Package layout:
```
src/image_providers/
    __init__.py       # re-exports generate_from_prompts, copy_provided_images, modify_images
    _routing.py       # copy_provided_images, modify_images, _dimensions_for_aspect, _ensure_env
    cloudflare.py     # _try_cloudflare
    siliconflow.py    # _try_siliconflow
    picsum.py         # _picsum_batch, _prompt_to_seed
    placeholder.py    # _generate_placeholder_images
    _http.py          # _http_post_with_retry, ProviderAuthError
```

`src/image_adapter.py` owns `generate_from_prompts` and `_native_ai_generation` (routing layer) and imports all helpers — so `patch.object(image_adapter, ...)` works correctly in tests.

---

## Step 6 — [x] Consolidate `subtitle_renderer.py` into `FFmpegSubtitleBackend`

Done. All production functions moved into `src/backends/ffmpeg_subtitle_backend.py`. `_render_subtitle_frame_legacy_test_only` moved into `tests/test_subtitle_renderer.py`. `src/subtitle_renderer.py` deleted.

Result: `orchestrator → FFmpegSubtitleBackend → ffmpeg`. No public interface changes.

---

## Step 7 — [x] Deprecate hardcoded `LANGUAGE_VOICES` dict in `tts_adapter.py`

Done. `LANGUAGE_VOICES` dict removed. `validate_voice_mappings()` reads from `config_loader.tts().language_voices`. `default_config.yaml` is the single source of truth. Tests updated.

---

## Unordered correctness fixes — all done

- **[x] TTS cache poisoning** — `_edge_tts` / `_openai_tts` return `(path, bool)` success flag; cache only written on `True`.
- **[x] `ImageClip` resource leak** — clips wrapped in `try/finally`, all closed on exit.
- **[x] `_color_to_ass` #RGB shorthand** — 4-char branch added before 7-char branch in `ffmpeg_subtitle_backend.py`.
- **[x] `VisualAssetConfig` bytes serialization** — `field_serializer` added with base64 encoding.
- **[x] `sanitize_filename` docstring** — dot-stripping behavior documented.

---

## Final state

```
python -m pytest tests/ -q              # 69 unit tests passing
python -m pytest -m integration        # 1 real assembly test passing
```

---

## Step 8 — [x] Introduce `VideoGateway` to decouple the orchestrator from adapter modules

**Files:** `src/gateway.py` (new), `src/orchestrator.py`, `src/main.py`, `src/ui.py`, `src/folder_watcher.py`

**Problem:** `VideoOrchestrator` imports four adapter modules directly (`tts_adapter`, `image_adapter`, `subtitle_adapter`, `assembler_adapter`) and calls their functions. This couples the use-case layer to concrete implementations. The Step 4 DI work already threads `ConfigLoader` through all adapter calls — but the orchestrator still knows *which* adapter to call, which means swapping or mocking an adapter requires patching the import in `src/orchestrator.py`.

**Fix:** Add a single `VideoGateway` dataclass that bundles the four adapter callables behind a clean interface:

```python
# src/gateway.py
from dataclasses import dataclass
from typing import Callable

@dataclass
class VideoGateway:
    generate_speech:    Callable
    generate_images:    Callable
    copy_images:        Callable
    assemble_video:     Callable
    generate_subtitles: Callable
```

`VideoOrchestrator.__init__` accepts an optional `gateway: VideoGateway = None`. When `None`, it builds a default one wired to the real adapters. The orchestrator stops importing any adapter module at all.

`main.py` (and `ui.py`, `folder_watcher.py`) become the only place that imports adapters — the wiring layer. Tests inject a `VideoGateway` built from plain lambdas or `MagicMock` callables instead of patching module internals with `patch("src.orchestrator.tts_adapter.generate_speech", ...)`.

**Architecture after this step:**
```
main.py               (framework / wiring — imports adapters, builds VideoGateway)
└─ VideoGateway       (interface adapter — concrete callables, already bound to ConfigLoader)
└─ VideoOrchestrator  (use case — only knows the gateway, no adapter imports)
└─ VideoConfiguration / PipelineResult  (entities — pure data, no dependencies)
```

**ConfigLoader consequence:** Once the gateway holds pre-wired callables (closures built in `main.py` that already captured the right `ConfigLoader`), the orchestrator no longer needs to forward `config_loader=self._config` at every call site. The config is resolved once at wiring time, not threaded through the call stack. The `config_loader` parameter on `VideoOrchestrator.__init__` can be retired.

**Test checkpoint:** Replace all `patch("src.orchestrator.tts_adapter.*")` fixtures in `test_orchestrator.py` with a `VideoGateway` built from mock callables passed directly to `VideoOrchestrator`. No module patching needed. Suite stays at 69+.

