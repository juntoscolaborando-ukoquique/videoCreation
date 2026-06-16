"""
CLI entry point for VideoCreation.

Usage::

    python -m src.main --config my_video.yaml
    python -m src.main --config my_video.json --output-dir /tmp/videos

Configuration files can be YAML or JSON and must match the
``VideoConfiguration`` schema (see src/schema.py or the README).
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from src.schema import VideoConfiguration
from src.orchestrator import VideoOrchestrator

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="videocreation",
        description="Generate a video from a YAML or JSON configuration file.",
    )
    parser.add_argument(
        "-c", "--config",
        required=True,
        metavar="FILE",
        help="Path to a .yaml, .yml, or .json configuration file.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "output"),
        metavar="DIR",
        help="Directory to save the generated video and workspace files.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        sys.exit(1)

    # Parse config file
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            suffix = config_path.suffix.lower()
            if suffix in (".yaml", ".yml"):
                raw = yaml.safe_load(f)
            elif suffix == ".json":
                raw = json.load(f)
            else:
                logger.error(
                    "Unsupported file format '%s'. Use .yaml, .yml, or .json.", suffix
                )
                sys.exit(1)
    except Exception as exc:
        logger.error("Failed to read configuration file: %s", exc)
        sys.exit(1)

    # Validate against schema
    try:
        config = VideoConfiguration(**raw)
    except Exception as exc:
        logger.error("Invalid configuration: %s", exc)
        sys.exit(1)

    # Run pipeline
    orchestrator = VideoOrchestrator(output_dir=args.output_dir)
    try:
        result = orchestrator.create_video(config)
        print(f"\nDone: {result.output_path}")
    except Exception as exc:
        logger.error("Video generation failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
