# VideoCreation

A configurable video generation pipeline that accepts user-defined content — speech text, visual assets, and styling options — and produces a complete video file.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    VideoOrchestrator                         │
│   (src/orchestrator.py — main pipeline)                     │
├──────────┬──────────┬───────────────┬───────────────────────┤
│          │          │               │                       │
│  TTS     │  Image   │  Subtitle     │  Assembler            │
│  Adapter │  Adapter │  Adapter      │  Adapter              │
│          │          │               │                       │
│ edge_tts │ Cloudflare │ Word-rate     │ moviepy               │
│ openai   │ SiliconFlow│ estimation    │ (injectable           │
│          │ Picsum     │               │  backend)             │
│          │ Pillow     │               │                       │
└──────────┴──────────┴───────────────┴───────────────────────┘
```

### Module Overview

| Module | Purpose |
|--------|---------|
| `src/schema.py` | Pydantic models for `VideoConfiguration`, `TTSBackend`, `ImageEngine` |
| `src/orchestrator.py` | Main pipeline: wires all adapters together |
| `src/tts_adapter.py` | Text-to-speech (edge_tts + silent fallback) |
| `src/image_adapter.py` | AI image generation (Cloudflare/SiliconFlow + Picsum/Pillow fallback) |
| `src/subtitle_adapter.py` | Subtitle segment generation (word-rate model) |
| `src/subtitle_renderer.py` | ffmpeg ASS-based subtitle burn-in (precise positioning, descender fix) |
| `src/assembler_adapter.py` | Final video assembly via moviepy (injectable `AssemblerBackend` for testing) |
| `src/backends/__init__.py` | `AssemblerBackend` and `SubtitleBackend` protocol definitions |
| `src/config_loader.py` | Reads and caches `config/default_config.yaml` |
| `src/ui.py` | Streamlit UI for interactive video generation |
| `src/main.py` | CLI entry point supporting YAML/JSON execution |
| `src/folder_watcher.py` | Directory watching daemon for asynchronous pipeline integration |
| `src/__main__.py` | Package entry point relaying to `src.main` |
| `config/default_config.yaml` | Default TTS/image/video/subtitle settings |

---

## Setup

### Prerequisites

- Python 3.10+
- ffmpeg (must be on `$PATH`)
- System fonts (DejaVu or Liberation — usually pre-installed on Linux)

### Install

```bash
cd /root/a_VIDEO_GENERATION/VIDEO_DESDE_PERSONAS/VideoCreation
pip install -r requirements.txt
```

---

## Usage

### CLI Usage

You can run the pipeline directly from the command line using a YAML or JSON configuration file:

```bash
# Run with an example configuration
python -m src.main --config config/example_english.yaml

# Alternatively, using the package relay
python -m src --config config/example_english.yaml
```

### UI Usage

For an interactive experience, you can use the Streamlit-based UI:

```bash
python -m streamlit run src/ui.py
```

The UI supports:
- **Interactive Configuration**: Set titles, speech content, and orientation.
- **Visual Asset Management**: Upload local images directly or provide AI prompts.
- **Real-time Logs**: Monitor the generation progress directly in the browser.
- **Video Preview**: Watch the generated video immediately after assembly.

### File-Based Integration API (Drop Folder)

To keep `VideoCreation` completely decoupled from any external applications or pipelines, we provide an asynchronous Drop Folder architecture. `VideoCreation` has zero knowledge of the applications triggering it. Any project in any language can simply generate a valid `.yaml` configuration and drop it into the inbox.

To start the watcher daemon:

```bash
./run_watcher.sh
```

This monitors the `watcher_folders/inbox/` directory. External projects simply write their `.yaml` or `.json` configuration file into that folder. The watcher automatically picks it up, moves it to `watcher_folders/processing/`, generates the video, and moves the config to `watcher_folders/done/` (or `watcher_folders/failed/` on error). 

This guarantees strict separation of concerns, prevents dependency conflicts, and allows external projects to trigger video rendering without blocking their own execution.

### Programmatic API

```python
from src.schema import VideoConfiguration, VisualAssetConfig, VisualAssetType
from src.orchestrator import VideoOrchestrator

config = VideoConfiguration(
    title="My First Video",
    speech_content="Welcome to our product demo. Let me show you the key features.",
    visual_assets=VisualAssetConfig(
        asset_type=VisualAssetType.TEXT_PROMPTS,
        prompts=[
            "A modern software dashboard with charts",
            "A team collaborating around a whiteboard",
        ],
    ),
    subtitles_enabled=True,
)

orchestrator = VideoOrchestrator(output_dir="output")
result = orchestrator.create_video(config)

print(f"Video saved: {result['output_path']}")
```

### Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | str | *required* | Video title |
| `language` | Language (str) | `Language.ENGLISH` | Target language for TTS |
| `speech_content` | str | *required* | Text converted to speech audio |
| `visual_assets` | VisualAssetConfig | *required* | Images or AI prompts |
| `length_seconds` | float \| None | None | Target duration in seconds (auto if None) |
| `background_music` | str \| None | None | Path to background audio |
| `image_modification_instructions` | str \| None | None | AI image editing instructions |
| `subtitles_enabled` | bool | False | Burn subtitles into the video |
| `output_format` | OutputFormat | mp4 | `mp4`, `mov`, `avi`, or `webm` |
| `orientation` | Orientation | `vertical` | `vertical` (9:16) or `horizontal` (16:9) |
| `tts_backend` | TTSBackend \| None | None | Per-video TTS backend override (`edge_tts`, `azure`, `openai`, `fish_tts`) |
| `tts_rate` | str \| None | None | Per-video speaking rate override (e.g. `"-10%"`, `"+5%"`) |
| `image_engine` | ImageEngine \| None | None | Per-video image engine override (`cloudflare`, `siliconflow`, `huggingface`, `pollinations`, `picsum`) |
| `image_style` | str \| None | None | Per-video image style override (e.g. `cinematic`, `photorealistic`) |

### Environment Variables

Create a `.env` file at the project root with your API keys:

```env
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_api_token
SILICONFLOW_API_KEY=your_key
HUGGINGFACE_API_KEY=your_key
```

All keys are optional — the pipeline falls through to the next available provider automatically.

---

```bash
# Run all tests with verbose output
python -m pytest tests/ -v

# Run only schema tests
python -m pytest tests/test_schema.py -v

# Run only orchestrator integration tests
python -m pytest tests/test_orchestrator.py -v

# Run only adapter unit tests
python -m pytest tests/test_adapters.py -v

# Run only subtitle renderer tests
python -m pytest tests/test_subtitle_renderer.py -v
```

All tests mock external dependencies (TTS, AI image generation, video assembly) so they run **fast** and **offline** — no API keys or network required.

### Test Flows Covered

1. **Minimal video** — images + speech, no subtitles, default mp4
2. **AI image generation** — text prompts instead of image files
3. **Video with subtitles** — subtitle burn-in enabled
4. **Background music** — music mixing path
5. **Custom output format** — `.webm` output
6. **Image modification** — verifies `modify_images` is called with the correct instruction string, and is not called when no instructions are set
7. **No visuals error** — validates proper error handling
8. **Subtitle renderer** — frame size, descender pixel check, text wrapping, empty text
9. **Assembler backend** — burn-in called/skipped, backend injection, moviepy import error

---

## Project Structure

```
VideoCreation/
├── config/
│   └── default_config.yaml
├── src/
│   ├── __init__.py
│   ├── schema.py
│   ├── orchestrator.py
│   ├── tts_adapter.py
│   ├── image_adapter.py
│   ├── subtitle_adapter.py
│   ├── subtitle_renderer.py
│   ├── assembler_adapter.py
│   ├── folder_watcher.py
│   ├── backends/
│   │   ├── __init__.py               # AssemblerBackend + SubtitleBackend protocols
│   └── config_loader.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_schema.py
│   ├── test_adapters.py
│   ├── test_subtitle_renderer.py
│   └── test_orchestrator.py
├── output/                    # Generated videos (gitignored)
├── watcher_folders/           # State folders for the drop watcher daemon (inbox, processing, etc.)
├── run_test_video.py
├── run_watcher.sh
├── Initial_prompt.md
├── ARCH_TO_DO.md
├── CHANGELOG.md
├── README.md
├── ROADMAP.md
└── requirements.txt
```

---
