"""
VideoGateway — interface adapter layer between the orchestrator and concrete adapters.

The orchestrator only knows this dataclass. Concrete adapter modules are imported
once, here, at wiring time. Tests inject plain callables; no module patching needed.

Usage (production)::

    from src.gateway import VideoGateway
    from src.config_loader import ConfigLoader

    cfg = ConfigLoader()
    gateway = VideoGateway.default(config_loader=cfg)
    orchestrator = VideoOrchestrator(output_dir="output", gateway=gateway)

Usage (tests)::

    gateway = VideoGateway(
        generate_speech=lambda **kw: write_stub(kw["output_path"]),
        generate_images=lambda prompts, output_dir, **kw: make_images(prompts, output_dir),
        copy_images=lambda paths, output_dir: copy_stubs(paths, output_dir),
        assemble_video=lambda **kw: write_stub(kw["output_path"]),
        generate_subtitles=lambda **kw: [],
        burn_subtitles=lambda video_path, **kw: video_path,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class VideoGateway:
    """Bundles all external I/O callables behind a single object.

    Each field is a plain callable. Signatures mirror the underlying adapter
    functions — see ``VideoGateway.default()`` for the concrete bindings.
    """

    generate_speech: Callable
    """generate_speech(text, output_path, *, voice, language, method, rate) -> str"""

    generate_images: Callable
    """generate_images(prompts, output_dir, *, style, engine, aspect_ratio, width, height) -> List[str]"""

    copy_images: Callable
    """copy_images(image_paths, output_dir) -> List[str]"""

    assemble_video: Callable
    """assemble_video(audio_path, visual_files, *, title, output_dir, output_format,
                      background_music, width, height, backend) -> str"""

    generate_subtitles: Callable
    """generate_subtitles(text, *, total_duration, words_per_second, max_words_per_chunk) -> List[Dict]"""

    burn_subtitles: Callable
    """burn_subtitles(video_path, segments, *, output_dir, output_filename, output_format, width, height) -> str"""

    modify_images: Callable
    """modify_images(image_paths, instructions) -> List[str]  (raises NotImplementedError until implemented)"""

    video_dimensions: Callable
    """video_dimensions() -> tuple[int, int]  returns (base_width, base_height) from config"""

    @staticmethod
    def default(config_loader=None) -> "VideoGateway":
        """Build a gateway wired to the real adapter modules.

        All config reads are resolved here using *config_loader* (or the
        module-level singleton when omitted).  The returned callables are
        plain closures — the orchestrator never sees ConfigLoader.

        Parameters
        ----------
        config_loader:
            Optional ``ConfigLoader`` instance. Defaults to the module singleton.
        """
        from src import tts_adapter, image_adapter, subtitle_adapter, assembler_adapter
        from src import config_loader as _default_config_loader
        from src.backends.ffmpeg_subtitle_backend import FFmpegSubtitleBackend

        _cfg = config_loader or _default_config_loader
        _subtitle_backend = FFmpegSubtitleBackend()

        def _generate_speech(text, output_path, *, voice=None, language=None, method=None, rate=None):
            return tts_adapter.generate_speech(
                text=text,
                output_path=output_path,
                voice=voice,
                language=language,
                method=method,
                rate=rate,
                config_loader=_cfg,
            )

        def _generate_images(prompts, output_dir, *, style=None, engine=None,
                              aspect_ratio=None, width=None, height=None):
            return image_adapter.generate_from_prompts(
                prompts,
                output_dir,
                style=style,
                engine=engine,
                aspect_ratio=aspect_ratio,
                width=width,
                height=height,
                config_loader=_cfg,
            )

        def _copy_images(image_paths, output_dir):
            return image_adapter.copy_provided_images(image_paths, output_dir)

        def _assemble_video(audio_path, visual_files, *, title="untitled", output_dir="output",
                            output_format="mp4", background_music=None, width=None,
                            height=None, backend=None):
            return assembler_adapter.assemble_video(
                audio_path=audio_path,
                visual_files=visual_files,
                title=title,
                output_dir=output_dir,
                output_format=output_format,
                background_music=background_music,
                width=width,
                height=height,
                backend=backend,
                config_loader=_cfg,
            )

        def _generate_subtitles(text, *, total_duration=None,
                                words_per_second=None, max_words_per_chunk=None):
            return subtitle_adapter.generate_subtitle_segments(
                text=text,
                total_duration=total_duration,
                words_per_second=words_per_second,
                max_words_per_chunk=max_words_per_chunk,
                config_loader=_cfg,
            )

        def _burn_subtitles(video_path, segments, *, output_dir, output_filename,
                            output_format, width, height):
            return _subtitle_backend.burn_subtitles(
                video_path=video_path,
                segments=segments,
                output_dir=output_dir,
                output_filename=output_filename,
                output_format=output_format,
                width=width,
                height=height,
                config_loader=_cfg,
            )

        def _modify_images(image_paths, instructions):
            return image_adapter.modify_images(image_paths, instructions)

        def _video_dimensions():
            cfg = _cfg.video()
            return cfg.get("width", 1080), cfg.get("height", 1920)

        return VideoGateway(
            generate_speech=_generate_speech,
            generate_images=_generate_images,
            copy_images=_copy_images,
            assemble_video=_assemble_video,
            generate_subtitles=_generate_subtitles,
            burn_subtitles=_burn_subtitles,
            modify_images=_modify_images,
            video_dimensions=_video_dimensions,
        )
