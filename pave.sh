#!/bin/bash
# === Prevent concurrent runs ===
LOCKFILE="/var/lock/pave.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "Another pave.sh is already running. Exiting." >&2
    exit 0
fi

DAY=$(date +%a)
NEXT_HOUR=$(date -d '+1 hour' +%H)
[ "$NEXT_HOUR" = "00" ] && DAY=$(date +%a -d "tomorrow")

# Clear only the true next hour
while read -r cam _ip; do
  d="$BASE_DIR/$cam/$DAY/$NEXT_HOUR"
  if [ -d "$d" ]; then
    rm -f "$d"/*
    echo "Cleared next: $d"
  fi
done < <(list_cams)

# Compress old footage
while read -r cam _ip; do
  while IFS= read -r -d '' f; do
    dir=$(dirname "$f")
    tarfile="$dir/${cam}_$(basename "$(dirname "$dir")")_$(basename "$dir")".tar.gz
    if [ ! -f "$tarfile" ]; then
      echo "Zipping $dir"

      tmp_tar=$(mktemp --tmpdir=/tmp "pave_${cam}_XXXXXX.tar.gz")

      # Only archive actual .mp4 files, write to temp first
      if nice -n 5 tar -czf "$tmp_tar" -C "$dir" --null -T <(find "$dir" -maxdepth 1 -name '*.mp4' -print0) --ignore-failed-read 2>/dev/null; then
        mv -f "$tmp_tar" "$tarfile"

        # Create index (best effort)
        find "$dir" -maxdepth 1 -name '*.mp4' -printf '%f\n' > "$tarfile.idx" || : > "$tarfile.idx"

        rm -f "$dir"/*.mp4
        echo "Done $dir"
      else
        echo "tar failed for $dir, keeping mp4 files" >&2
        rm -f "$tmp_tar" "$tarfile"
      fi
    fi
  done < <(find "$BASE_DIR/$cam" -name "*.mp4" -mmin +180 -print0 2>/dev/null)
done < <(list_cams)

echo "Pave finished $(date)"