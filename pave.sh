#!/bin/bash
# Compresses footage older than 3 hours into per-hour tarballs and clears the
# upcoming hour's folder so new recordings have a clean place to land.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.sh"

DAY=$(date +%a)
NEXT_HOUR=$(date -d '+1 hour' +%H)
[ "$NEXT_HOUR" = "00" ] && DAY=$(date +%a -d "tomorrow")

# Clear only the true next hour (safer than touching anything else).
while read -r cam _ip; do
  d="$BASE_DIR/$cam/$DAY/$NEXT_HOUR"
  if [ -d "$d" ]; then
    rm -f "$d"/*
    echo "Cleared next: $d"
  fi
done < <(list_cams)

# Compress folders whose MP4s are older than 3 hours.
while read -r cam _ip; do
  while IFS= read -r -d '' f; do
    dir=$(dirname "$f")
    tarfile="$dir/${cam}_$(basename "$(dirname "$dir")")_$(basename "$dir").tar.gz"
    if [ ! -f "$tarfile" ]; then
      echo "Zipping $dir"
      # Only delete the MP4s if the archive was created successfully.
      if nice -n 15 tar -czf "$tarfile" -C "$dir" --exclude='*.gz' --ignore-failed-read . ; then
        # Write a lightweight index of the archived mp4 names so the HTTP API
        # can list segments without decompressing the whole tarball.
        ls -1 "$dir"/*.mp4 2>/dev/null | xargs -r -n1 basename > "$tarfile.idx"
        rm -f "$dir"/*.mp4
        echo "→ Done $dir"
      else
        echo "✗ tar failed for $dir, keeping mp4 files" >&2
        rm -f "$tarfile"
      fi
    fi
  done < <(find "$BASE_DIR/$cam" -name "*.mp4" -mmin +180 -print0 2>/dev/null)
done < <(list_cams)

echo "Pave finished $(date)"
