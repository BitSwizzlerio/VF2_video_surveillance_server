#!/bin/bash

# ====================== CONFIGURATION ======================
BASE_DIR="/mnt/nvme"      # Change this if you want it elsewhere (e.g. ./nvme)
NUM_CAMS=4                # How many cameras you want (cam1 to camN)
# ===========================================================

DAYS=("Sun" "Mon" "Tue" "Wed" "Thu" "Fri" "Sat")

echo "Creating directory structure under: $BASE_DIR"
echo "Number of cameras: $NUM_CAMS"
echo

for cam_num in $(seq 1 "$NUM_CAMS"); do
    cam_dir="$BASE_DIR/cam${cam_num}"
    mkdir -p "$cam_dir"
    echo "  → Created $cam_dir"

    for day in "${DAYS[@]}"; do
        day_dir="$cam_dir/$day"
        mkdir -p "$day_dir"

        for hour in $(seq -w 0 23); do
            mkdir -p "$day_dir/$hour"
        done
    done
done

echo
echo "✅ Done! Full structure created for cam1 through cam${NUM_CAMS}"
echo "You can now start your cam*.sh scripts."
