import argparse
import json
import logging
import shutil
import sys
import time
import traceback
from pathlib import Path

import yaml

from src.schema import VideoConfiguration
from src.orchestrator import VideoOrchestrator
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)


class FolderWatcher:
    def __init__(self, base_dir: Path, output_dir: Path, poll_interval: int = 5):
        self.base_dir = base_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.poll_interval = poll_interval

        self.inbox_dir = self.base_dir / "inbox"
        self.processing_dir = self.base_dir / "processing"
        self.done_dir = self.base_dir / "done"
        self.failed_dir = self.base_dir / "failed"

        self._setup_directories()
        self.orchestrator = VideoOrchestrator(output_dir=str(self.output_dir))

    def _setup_directories(self):
        for directory in [self.inbox_dir, self.processing_dir, self.done_dir, self.failed_dir, self.output_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info("Ensured directory exists: %s", directory)

    def _process_file(self, file_path: Path):
        logger.info("Found new file: %s", file_path.name)
        
        # Move to processing
        processing_path = self.processing_dir / file_path.name
        try:
            shutil.move(str(file_path), str(processing_path))
            logger.info("Moved %s to processing.", file_path.name)
        except Exception as e:
            logger.error("Failed to move file %s to processing: %s", file_path.name, e)
            return

        success = False
        try:
            # Parse config file
            with open(processing_path, "r", encoding="utf-8") as f:
                suffix = processing_path.suffix.lower()
                if suffix in (".yaml", ".yml"):
                    raw = yaml.safe_load(f)
                elif suffix == ".json":
                    raw = json.load(f)
                else:
                    raise ValueError(f"Unsupported file format '{suffix}'.")
            
            if not raw:
                 raise ValueError("Configuration file is empty or invalid.")

            # Validate against schema
            config = VideoConfiguration(**raw)

            # Clean up any stale workspace from a previous failed run with the same title
            workspace = self.output_dir / sanitize_filename(config.title)
            if workspace.exists():
                logger.warning("Stale workspace found for '%s' — cleaning before retry.", config.title)
                shutil.rmtree(workspace, ignore_errors=True)

            # Run pipeline
            logger.info("Starting video generation for: %s", config.title or processing_path.name)
            result = self.orchestrator.create_video(config)
            logger.info("Successfully created video: %s", result.output_path)
            success = True

        except Exception as exc:
            logger.error("Error processing %s:\n%s", processing_path.name, traceback.format_exc())

        # Move to final destination
        try:
            dest_dir = self.done_dir if success else self.failed_dir
            dest_path = dest_dir / processing_path.name
            
            # Handle case where a file with the same name already exists in destination
            if dest_path.exists():
                timestamp = int(time.time())
                dest_path = dest_dir / f"{processing_path.stem}_{timestamp}{processing_path.suffix}"
                
            shutil.move(str(processing_path), str(dest_path))
            logger.info("Moved %s to %s.", processing_path.name, dest_dir.name)
        except Exception as e:
            logger.error("Failed to move file %s from processing: %s", processing_path.name, e)

    def run(self):
        logger.info("Starting folder watcher polling every %s seconds.", self.poll_interval)
        logger.info("Watching directory: %s", self.inbox_dir)
        try:
            while True:
                # Note: Currently processes one file at a time (sequentially).
                # If generation takes 5 mins and 3 files drop, they will queue up silently.
                # See ROADMAP for future concurrent/async processing improvements.
                for ext in ["*.yaml", "*.yml", "*.json"]:
                    for file_path in self.inbox_dir.glob(ext):
                        if file_path.is_file():
                            self._process_file(file_path)
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("Folder watcher stopped by user.")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    parser = argparse.ArgumentParser(
        prog="folder_watcher",
        description="Watch a folder for YAML/JSON configurations and automatically generate videos.",
    )
    parser.add_argument(
        "-w", "--watch-dir",
        default=str(Path(__file__).resolve().parent.parent / "watcher_folders"),
        metavar="DIR",
        help="Base directory for the watcher (will contain inbox/, processing/, etc.).",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "output"),
        metavar="DIR",
        help="Directory to save the generated videos.",
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=5,
        metavar="SECONDS",
        help="Polling interval in seconds.",
    )
    args = parser.parse_args()

    watcher = FolderWatcher(
        base_dir=Path(args.watch_dir),
        output_dir=Path(args.output_dir),
        poll_interval=args.interval
    )
    watcher.run()


if __name__ == "__main__":
    main()
