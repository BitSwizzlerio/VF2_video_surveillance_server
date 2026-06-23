#!/bin/bash
# Central configuration for the VF2 video surveillance scripts.
# Every other script sources this file, so you only edit settings in one place.
#
#   . "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.sh"

# Directory this config lives in (all scripts are expected to sit together).
CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Where the scripts live (used by the watchdog to relaunch recorders).
SCRIPT_DIR="$CONFIG_DIR"

# Root of the NVMe storage where all footage is written.
BASE_DIR="/mnt/nvme"

# Length of each recording segment, in seconds (900 = 15 minutes).
DURATION=900

# ESP32-CAM frame size sent to the camera's /control endpoint (12 = SVGA).
FRAMESIZE=12

# How many days to keep compressed (.tar.gz) footage before deleting it.
RETENTION_DAYS=2

# Camera -> IP mapping file (one "name ip" pair per line).
CAMS_CONF="$CONFIG_DIR/cams.conf"

# Log files.
CLEANUP_LOG="/var/log/video_cleanup.log"
WATCHDOG_LOG="/var/log/cam_watchdog.log"

# Print "name ip" for each configured camera.
# Blank lines and lines starting with # are ignored.
list_cams() {
    while read -r _name _ip _rest; do
        [ -z "$_name" ] && continue
        case "$_name" in \#*) continue ;; esac
        printf '%s %s\n' "$_name" "$_ip"
    done < "$CAMS_CONF"
}
