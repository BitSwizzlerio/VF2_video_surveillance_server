#!/bin/bash
# Pre-creates the cam/day/hour folder tree on the NVMe for every camera in
# cams.conf. Safe to run repeatedly (mkdir -p never clobbers existing data).
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.sh"

DAYS=("Sun" "Mon" "Tue" "Wed" "Thu" "Fri" "Sat")

echo "Creating directory structure..."
while read -r cam _ip; do
    for day in "${DAYS[@]}"; do
        for hour in $(seq -w 0 23); do
            mkdir -p "$BASE_DIR/$cam/$day/$hour"
        done
    done
    echo "→ $cam done"
done < <(list_cams)
echo "✅ Folder structure created for all cameras in $CAMS_CONF"