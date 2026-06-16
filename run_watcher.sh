#!/bin/bash
# run_watcher.sh - Convenience script to start the drop folder watcher

# Ensure we're in the right directory
cd "$(dirname "$0")"

echo "Starting VideoCreation Folder Watcher..."
echo "Press Ctrl+C to stop."

# Run the watcher module
python3 -m src.folder_watcher "$@"
