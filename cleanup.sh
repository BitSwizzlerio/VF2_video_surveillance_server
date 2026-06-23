#!/bin/bash
# Deletes compressed footage older than RETENTION_DAYS (configured in config.sh).
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.sh"

echo "=== Video Cleanup Started at $(date) ===" | tee -a "$CLEANUP_LOG"

# Only delete old .tar.gz archives (live .mp4 files are left untouched).
while IFS= read -r -d '' file; do
    echo "Deleting old file: $file" | tee -a "$CLEANUP_LOG"
    rm -f "$file" "$file.idx"
done < <(find "$BASE_DIR" -type f -name "*.tar.gz" -mtime +"$RETENTION_DAYS" -print0)

echo "=== Cleanup Completed at $(date) ===" | tee -a "$CLEANUP_LOG"
