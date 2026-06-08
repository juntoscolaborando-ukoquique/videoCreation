# Changelog

## [Unreleased]

## [0.3.0] - 2026-06-08

### Added
- `config/sylvia_2_es.yaml` — new video prompt for Sylvia, a retired teacher, using rioplatense Spanish, Cloudflare AI images, `-10%` TTS rate, and vertical orientation.
- `config/test_cloudflare.yaml` — minimal smoke-test config to verify Cloudflare AI image generation end-to-end.
- `TROUBLESHOOTING.md` — two new entries: "Picsum images don't match prompts" and "Pollinations returns HTTP 402 on VPS/cloud servers" with root cause analysis and fix options.

### Fixed
- `src/image_adapter.py` — Picsum requests now use `allow_redirects=True`; previously the 302 redirect was not followed, silently returning empty responses.
- `src/image_adapter.py` — Picsum is no longer the default provider. It is now only used when `image_engine: picsum` is explicitly set. All other cases go directly to `FootageGeneratorV2` (Cloudflare → SiliconFlow → HuggingFace → Picsum fallback), ensuring AI-generated images that match the prompt.
- `src/image_adapter.py` — `_try_footage_generator()` now explicitly passes `cloudflare_account_id`, `cloudflare_token`, and `siliconflow_key` from environment variables to `FootageGeneratorV2`, enabling the full provider failover chain.

### Changed
- `src/image_adapter.py` — `dotenv` loaded at module import so `.env` credentials are available without manual setup.
- Default image provider priority is now: Cloudflare Workers AI → SiliconFlow → Pollinations (blocked on VPS, skipped) → HuggingFace → Picsum.

## [0.2.0] - 2026-06-07

### Added
- **Filesystem-Safe Filenames** (`assembler_adapter.py`): New `_sanitize_filename()` helper strips all filesystem-unsafe characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`, null bytes), replaces spaces with underscores, collapses consecutive underscores, and falls back to `"untitled"` for blank results. Output filenames are now safe across all operating systems.
- **Dynamic ASS Font Name** (`subtitle_renderer.py`): New `_FONT_NAME_MAP` lookup table and `_font_name_from_path()` function derive the correct ASS font family name from the configured font file path, instead of hardcoding `"Liberation Sans"`. Supports Liberation Sans/Serif, DejaVu Sans, and Arial out of the box; unknown fonts get a best-effort capitalized name.
- **OpenAI TTS Support**: Added a native OpenAI TTS dispatcher in `src/tts_adapter.py`. Config can now specify `method: "openai"` to use official OpenAI voices (requires `openai` package and `OPENAI_API_KEY`).
- **TTS Audio Caching**: Implemented MD5-based caching for generated audio in `src/tts_adapter.py`. Consecutive identical text-to-speech requests now hit `.cache/tts/`, vastly speeding up video generation with unchanged scripts.
- **UI Improvements**: Added a direct file uploader to `src/ui.py`, allowing users to drag and drop local images instead of manually typing paths.
- **Path Detection Warning**: Added automatic detection in the AI Prompt text area of the UI to warn users if they accidentally enter file paths while in AI generation mode.
- **Scene-based Roadmap Entry**: Added "Scene-based Precision Mode" to `ROADMAP.md` (Phase 4), with a reference to the `TANDA_3/VideoCreation-06-FALLIDO-MODO_ESCENAS` folder for future implementation.

### Changed
- **Thread-Safe Config Loader** (`config_loader.py`): `load()` and `_clear_cache()` are now protected by a `threading.Lock`, preventing race conditions when multiple pipeline threads read config simultaneously. Config is loaded into a temporary dict before updating the cache, and `load()` returns a defensive copy (`dict(_cache)`) to prevent callers from mutating the shared state.
- **Scoped UI Logger** (`ui.py`): `_run_pipeline()` now attaches the queue handler to `logging.getLogger("src")` instead of the root logger. This isolates pipeline logs to the `src.*` namespace, preventing log pollution across concurrent Streamlit sessions.
- **Explicit `modify_images` Failure** (`image_adapter.py`): `modify_images()` now raises `NotImplementedError` with a clear message instead of silently returning unmodified images. Users who set `image_modification_instructions` in their config will get an immediate, actionable error telling them to remove the key until the feature is implemented.
- **TTS Decoupling**: Completely removed `ensure_lingo_on_path` from `src/tts_adapter.py`. The text-to-speech module is now fully decoupled from `Lingo_PERSONAS` and runs natively.

### Fixed
- **Width/Height Falsy-Zero Bug** (`assembler_adapter.py`): Replaced `width = width or cfg.get(...)` with `if width is None` guards. Previously, passing `width=0` or `height=0` would silently fall back to config defaults due to Python's truthiness semantics.
- **Subtitle Output Collision** (`subtitle_renderer.py`): Output filename now includes a UUID-based `run_id` (`subtitled_{run_id}_{filename}`), preventing file overwrites when multiple subtitle burn-in passes run against the same source video.
- **Subtitle Positioning**: Updated `src/subtitle_renderer.py` and `config/default_config.yaml` to support a configurable `position` ("bottom" or "middle") and adjusted the default `margin` from 300 to 50 pixels for better vertical alignment.
- **Subtitle Line Optimization**: Adjusted `max_words_per_chunk` (10 -> 8) and `max_chars_per_line` (32 -> 42) to ensure subtitles typically fit in 1 or 2 lines instead of 3.
- **Audio Guard in Subtitles**: Added a check in `src/subtitle_renderer.py` to handle videos without audio tracks, preventing crashes during the subtitle burn-in process.
- **Resource Scope Fix**: Moved `output_path` definition in `src/assembler_adapter.py` to the very top of `_local_moviepy_assemble` to prevent `UnboundLocalError` when assembly fails before assignment.
- **Assembly Guard**: Added a runtime check in `src/orchestrator.py` to ensure `assemble_video` returns a valid path and the file exists before finishing.
- **Lingo Path Priority**: Updated `src/lingo_utils.py` to give `LINGO_ROOT` and config settings priority over the `vendor/` directory, ensuring the correct version of Lingo_PERSONAS is always used.
- **Relative Path Stability**: Forced `output_dir` to be an absolute path in `src/ui.py`, `src/orchestrator.py`, and `src/main.py`. Also updated `run_test_video.py` and `orchestrator.py` docstrings for consistency.
- **Asyncio Loop Conflict**: Implemented a `ThreadPoolExecutor` wrapper in `src/tts_adapter.py` using a lambda to ensure the coroutine is created and run within the worker thread, fixing `RuntimeError: This event loop is already running`.
- **Picsum Batch Integrity**: Updated `src/image_adapter.py` to discard partial Picsum results if the batch is incomplete. This forces a fallback to AI generation to ensure the number of images matches the number of prompts, maintaining video synchronization.
- **Subtitle Performance Boost**: Replaced moviepy-based subtitle burn-in with an ffmpeg-based approach in `src/subtitle_renderer.py`. This reduces processing time from ~35 minutes to less than 1 minute for long videos by using the `subtitles` filter and stream copying audio.
- **FFmpeg Path Escaping**: Improved SRT and font path escaping in `src/subtitle_renderer.py`. The `subtitles` filter now uses an explicit `fontsdir` and references the exact font family name ("Liberation Sans") for robust rendering across environments.
- **Subtitle Sync Improvement**: `src/orchestrator.py` now measures the actual generated audio duration to scale subtitle segments when `length_seconds` is not provided, ensuring better synchronization.
- **Progress Tracking Fix**: Reworked step log numbering in `src/orchestrator.py` to a 4-step pipeline (`[1/4]`–`[4/4]`) covering the mandatory steps. The optional image modification step is logged as `[+]` when active and suppressed at DEBUG level when skipped, avoiding a misleading fixed denominator.

### Tests
- `test_modify_images_passthrough` renamed to `test_modify_images_raises_not_implemented` and updated to assert `NotImplementedError` is raised.
- TTS mock assertions updated to include the `rate` parameter (`'+0%'`) matching the current `_edge_tts` signature.

## [0.1.0] - 2026-06-06

### Added
- `src/schema.py` — added `PICSUM`, `UNSPLASH`, and `PEXELS` to `ImageEngine` enum to prepare for UI provider dropdowns
- `src/image_adapter.py` — added `_picsum_batch()` fallback function that fetches deterministic stock images from picsum.photos using prompt-keyword-derived seeds
- `config/demo_picsum.yaml` — new example configuration file demonstrating the Picsum fallback
- `config/default_config.yaml` — added `use_picsum` boolean flag to the `image` block (defaulting to `true`) to allow disabling the network-dependent Picsum fallback offline

### Fixed
- `src/assembler_adapter.py` — `_local_moviepy_assemble()` now properly crop-to-fills visual assets that don't match the target aspect ratio, eliminating letterboxing and pillarboxing
- `src/image_adapter.py` — `generate_from_prompts()` routing logic now respects an explicitly passed `engine` parameter (e.g. `engine="pollinations"` skips Picsum entirely); previously the routing only checked the global `use_picsum` config flag
- `src/subtitle_renderer.py` — `burn_subtitles()` now wraps `VideoFileClip` and `VideoClip` in `try/finally` blocks; `video.close()` and `composite.close()` are guaranteed to run even if an exception is raised mid-function, preventing file handle and ffmpeg subprocess leaks
- `src/assembler_adapter.py` — `_local_moviepy_assemble()` now wraps clip operations in nested `try/finally` blocks; `audio.close()` and `video.close()` are guaranteed to run on exception, preventing resource leaks when multiple videos are generated in a session
- `src/config_loader.py` — `load()` now catches `FileNotFoundError` and re-raises with the full resolved path to `default_config.yaml` and a hint to check the project root; previously a missing config would surface as a bare `FileNotFoundError` with no context
- `src/subtitle_renderer.py` — `burn_subtitles()` early-return warning now includes the reason and a hint about what to check (`text` non-empty, `end > start`), making silent subtitle drops visible to the caller
- `src/subtitle_renderer.py` — `render_subtitle_frame()` clamps `stroke_width` to a maximum of 8 to prevent O(stroke_width²) render cost from a large config value
- `src/image_adapter.py` — `modify_images()` stub promoted from `logger.info` to `logger.warning` with an explicit "NOT YET IMPLEMENTED" message; users setting `image_modification_instructions` now get visible feedback that no modification was applied
- `src/image_adapter.py` — `_try_footage_generator()` exception handling split into two blocks: import/path failures (Lingo not installed) fall back silently to placeholders; runtime errors from Lingo code are logged at `ERROR` level and re-raised so genuine bugs are not swallowed

### Added
- `config/test_quick.yaml` — minimal smoke-test config for quick end-to-end pipeline verification via CLI

### Fixed
- `src/image_adapter.py` — `_try_footage_generator()` was passing `provider=resolved_engine` to `FootageGeneratorV2.generate_images_batch()`, which the installed Lingo_PERSONAS version does not accept; this caused every AI image generation call to fail silently and fall back to Pillow placeholders. Removed the unsupported kwarg — the provider architecture is configured at `FootageGeneratorV2` construction time. Real Pollinations/HuggingFace image generation now works correctly.
- `src/subtitle_adapter.py` — `words_per_second`, `max_words_per_chunk`, and `total_duration` checks replaced `or`-based falsy fallback with explicit `is None` guards; previously passing `0` or `0.0` was silently ignored and the config default was used instead
- `src/subtitle_adapter.py` — `total_duration` scaling condition changed from `if total_duration` to `if total_duration is not None and total_duration > 0`; `total_duration=0` was previously treated as "not provided" due to falsiness
- `src/tts_adapter.py` — `method` resolution replaced `or`-based fallback with `if method is None`; passing an empty string no longer silently falls back to `edge_tts`
- `src/image_adapter.py` — `style`, `aspect_ratio`, `width`, and `height` resolution replaced `or`-based fallbacks with `if X is None` guards throughout `generate_from_prompts` and `_generate_placeholder_images`
- `src/orchestrator.py` — video title sanitization replaced `title.replace(" ", "_")` with `_sanitize_title()`, which strips all filesystem-unsafe characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`, null bytes), collapses consecutive underscores, and falls back to `"untitled"` for blank results; previously a title like `"My/Video"` would silently create nested directories

### Changed
- `src/orchestrator.py` — added `_sanitize_title()` helper function; `create_video()` now uses it instead of the bare `.replace(" ", "_")` call

### Roadmap corrections
- `ROADMAP.md` Phase 3 — marked three items as already complete: Pollinations integration, HuggingFace Flux/SDXL provider with automatic failover, and image style preset support; all three are implemented in Lingo_PERSONAS `FootageGeneratorV2` and were already being exercised by the adapter

---

### Added
- `src/subtitle_renderer.py` — new module with `burn_subtitles()` and `render_subtitle_frame()`; extracted from `assembler_adapter.py` so subtitle rendering is independently testable and extensible
- `src/backends/__init__.py` — `AssemblerBackend` protocol defining the stable interface all assembler backends must satisfy
- `src/backends/lingo_assembler_backend.py` — `LingoAssemblerBackend` class encapsulating all Lingo_PERSONAS VideoAssembler interaction; `assembler_adapter` no longer has direct knowledge of Lingo's API surface
- `src/schema.py` — `TTSBackend` and `ImageEngine` enums; `VideoConfiguration` gains three optional per-video override fields: `tts_backend`, `image_engine`, `image_style`
- `tests/test_subtitle_renderer.py` — dedicated test file for `subtitle_renderer`; moved from `TestSubtitleRenderer` in `test_adapters.py`
- `run_test_video.py` — smoke-test script for manual end-to-end pipeline verification
- `src/main.py` and `src/__main__.py` — clean CLI implementation supporting both YAML and JSON configs, with proper error surfacing
- `config/example_english.yaml` and `config/example_spanish.yaml` — useful reference documents for testing the CLI
- `src/ui.py` — new Streamlit application providing an interactive window UI for configuring and generating videos
- `requirements.txt` — added `streamlit>=1.20.0` dependency for the new UI

### Changed
- `src/assembler_adapter.py` — subtitle burn-in delegated to `subtitle_renderer.burn_subtitles()`; Lingo interaction delegated to `LingoAssemblerBackend`; file reduced from ~390 lines to ~110
- `src/assembler_adapter.py` — `_burn_subtitles` alpha compositing replaced: `CompositeVideoClip` with RGBA `ImageClip` (broken — transparent pixels rendered as black) replaced with a `VideoClip(make_frame)` approach that does per-frame Porter-Duff alpha blending via numpy; subtitles now render correctly
- `src/image_adapter.py` — `generate_from_prompts` and `_try_footage_generator` accept an `engine` parameter; per-video `image_engine` override takes precedence over config default
- `src/tts_adapter.py` — `generate_speech` forwards the per-video `tts_backend` value as `method` when set
- `src/orchestrator.py` — passes `tts_backend` and `image_engine`/`image_style` from `VideoConfiguration` down to the respective adapters
- `tests/test_adapters.py` — `TestSubtitleRenderer` removed (moved to `test_subtitle_renderer.py`); `TestAssemblerAdapter` updated to mock `LingoAssemblerBackend` and `subtitle_renderer.burn_subtitles` instead of the removed private functions
- `src/schema.py` — `VideoConfiguration` gains a `language` field as a string enum (`Language.ENGLISH` default), supporting multi-language TTS
- `src/schema.py` — `VideoConfiguration` gains an `orientation` field using a new `Orientation` string enum (`VERTICAL`, `HORIZONTAL`), defaulting to vertical
- `src/orchestrator.py` — `create_video` now calculates `aspect_ratio`, `width`, and `height` based on the chosen orientation and dynamically passes them to downstream adapters
- `src/image_adapter.py` — `generate_from_prompts` and `_generate_placeholder_images` updated to explicitly accept and use `width` and `height`, ensuring generated and placeholder images respect the requested orientation
- `src/assembler_adapter.py` — Backend injection improved with a module-level `_default_backend = LingoAssemblerBackend()` instantiated once and passed via `backend=` parameter to `assemble_video`, replacing fragile mock patching

### Fixed
- Subtitle burn-in was silently producing videos with no visible subtitles due to moviepy's `CompositeVideoClip` not alpha-blending RGBA `ImageClip` layers; fixed by switching to explicit per-frame numpy alpha blending in `subtitle_renderer.burn_subtitles`


### Added
- `src/lingo_utils.py` — shared module centralising `LINGO_ROOT` and `ensure_lingo_on_path()`, replacing three identical copies spread across adapters
- `src/config_loader.py` — reads `config/default_config.yaml` and exposes typed accessors (`tts()`, `image()`, `video()`, `subtitles()`); all previously hardcoded values now come from config

### Fixed
- `src/assembler_adapter.py` — moviepy fallback was resizing clips by `width` only, ignoring `height`; fixed to resize by `height` for correct portrait output
- `src/orchestrator.py` — step log labels were `1/5`–`5/5` across 4 logical steps; corrected to `1/4`–`4/4`
- `src/orchestrator.py` — removed redundant `float()` cast on `length_seconds` (type is now `float` at the schema level)
- `src/tts_adapter.py` — replaced `os.system()` string-interpolated ffmpeg call with `subprocess.run()` using an argument list; errors are now captured and logged
- `src/schema.py` — `length_seconds` changed from `Optional[int]` to `Optional[float]` since duration is naturally fractional

### Changed
- `src/tts_adapter.py`, `src/image_adapter.py`, `src/assembler_adapter.py`, `src/subtitle_adapter.py` — all hardcoded defaults (voice, image style, aspect ratio, width, height, fps, words_per_second, max_words_per_chunk) replaced with values read from `config/default_config.yaml` via `config_loader`
- `src/tts_adapter.py`, `src/image_adapter.py`, `src/assembler_adapter.py` — removed duplicated `LINGO_ROOT` / `_ensure_lingo_on_path` definitions; now import from `src/lingo_utils`

### Removed
- `pydub` dependency — was listed in `requirements.txt` but never imported anywhere
- `requests` dependency — was listed in `requirements.txt` but never imported anywhere
- `docs/` — empty directory removed
- Unused `shutil` import in `tests/conftest.py`
- `os.system()` f-string ffmpeg call in `tests/conftest.py` — replaced with `subprocess.run()` using an argument list, consistent with the same fix applied to `tts_adapter.py`; also removed the now-unused `os` import

### Tests
- `tests/test_orchestrator.py` — `_patch_adapters` fixture now yields `{"modify_images": mock}` exposing the `MagicMock` to tests that need it; `TestImageModification` replaced with two spy tests: one asserting `modify_images` is called exactly once with the correct instruction string, one asserting it is never called when no instructions are set
- `tests/test_adapters.py` — added `test_no_empty_segments_from_trailing_punctuation` covering text ending with punctuation + trailing whitespace or newline, which previously produced empty subtitle segments

### Fixed (continued)
- `src/subtitle_adapter.py` — sentence split via `re.split(r'(?<=[.!?])\s+', ...)` could produce empty string elements when input text ended with punctuation followed by whitespace; fixed by filtering blank sentences with `if s.strip()` and using `text.strip()` in the fallback chunk path
- `src/assembler_adapter.py` — `_local_moviepy_assemble` did not receive `subtitles_enabled` or `segments`; both are now forwarded so the signature is complete and future caption support won't require a breaking change
- `src/assembler_adapter.py` — when Lingo is unavailable and subtitles are requested, a warning is now logged at the decision point in `assemble_video` before the fallback is called; previously subtitles were silently dropped with no indication to the caller
- `src/assembler_adapter.py` — `from moviepy.video.fx import Resize` is now wrapped in a `try/except ImportError` that raises a `RuntimeError` with a clear message and version hint; previously a broken moviepy install would surface as a confusing `NameError` or `AttributeError` deep in the assembly loop
- `requirements.txt` — `moviepy>=2.0.0.dev2` pinned to `==2.1.2` (the tested version) to prevent a future breaking 2.x release from silently corrupting the fallback assembler
- `src/config_loader.py` — module-level `_cache` dict persisted across tests, allowing a patched config load in one test to pollute subsequent tests; added `_clear_cache()` and an `autouse` fixture in `tests/conftest.py` that clears the cache before and after every test
- `src/lingo_utils.py` — `LINGO_ROOT` was a hardcoded absolute path in code; now resolved at runtime in priority order: `LINGO_ROOT` env var → `lingo.root` in `config/default_config.yaml` → hardcoded default with a `WARNING` log; `config/default_config.yaml` gains a `lingo.root` key and `config_loader` gains a `lingo()` accessor
- `src/orchestrator.py` — step log labels were inconsistent after earlier edits (steps 2/4 appeared twice, then 5/5 appeared without a matching total); corrected to a consistent `1/5`–`5/5` matching the actual 5 pipeline steps
- `README.md` — updated to reflect all code changes: `length_seconds` type corrected to `float | None`, `docs/` removed from project structure, `src/lingo_utils.py` and `src/config_loader.py` added to module overview and structure tree, `CHANGELOG.md` added to structure tree, test flow list expanded from 7 to 9 entries with accurate descriptions
- `tests/test_adapters.py` — `test_moviepy_import_error_raises_runtime_error` replaced fragile `patch.dict(sys.modules, {"moviepy": None})` approach (order-sensitive, relies on CPython `None`-in-sys.modules behaviour) with a `types.ModuleType` subclass whose `__getattr__` raises `ImportError`; reliable regardless of prior import state in the test session

### Added (subtitle rendering overhaul)
- `src/assembler_adapter.py` — `_burn_subtitles()` — new function that composites subtitle frames onto an assembled video using moviepy `CompositeVideoClip`; runs as a post-pass after Lingo or the local fallback produces the base video
- `src/assembler_adapter.py` — `_render_subtitle_frame()` — renders one RGBA subtitle frame using Pillow; line height is derived from `font.getmetrics()` (ascent + descent) rather than `textbbox`, which only returns the ink bounding box and clips descenders for characters like p, q, g, y, j
- `config/default_config.yaml` — added `subtitles.max_chars_per_line: 32` to control text wrapping before burn-in
- `requirements.txt` — added `numpy>=1.24.0` (used by `_burn_subtitles` to convert Pillow RGBA frames to moviepy-compatible arrays)

### Changed (subtitle rendering overhaul)
- `src/assembler_adapter.py` — subtitle rendering ownership moved from Lingo to this adapter; `_try_lingo_assembler` now always passes `add_captions=False` and no longer forwards `segments` or `subtitles_enabled` — those are handled entirely by `_burn_subtitles`
- `src/assembler_adapter.py` — `assemble_video` flow changed: base video is assembled first (Lingo or local fallback, no captions), then `_burn_subtitles` is called as a separate step if `subtitles_enabled=True`
- `config/default_config.yaml` — `subtitles.font_size` bumped from `36` to `54` (50% larger, user-visible improvement); `subtitles.margin` bumped from `200` to `300` to keep text clear of the frame edge at the larger size

### Tests (subtitle rendering overhaul)
- `tests/test_adapters.py` — added `TestSubtitleRenderer` class with four tests: `test_frame_is_correct_size`, `test_descenders_not_clipped` (pixel-level numpy check that rendered height ≥ ascent + descent), `test_long_text_wrapped`, `test_empty_text_returns_transparent_frame`
- `tests/test_adapters.py` — `TestAssemblerAdapter` rebuilt: replaced warning-based tests with four behaviour tests: `test_subtitle_burn_in_called_when_enabled`, `test_subtitle_burn_in_skipped_when_disabled`, `test_local_fallback_used_when_lingo_unavailable`, `test_lingo_called_without_captions` (asserts `add_captions=False` is always enforced)
