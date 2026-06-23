#!/bin/bash
# Records a single camera's MJPEG stream into hourly folders on the NVMe.
#
# Usage: cam.sh <cam-name> <camera-ip>
#   e.g. cam.sh cam1 192.168.0.83
#
# Normally you don't call this directly. The watchdog launches one instance per
# camera using the values from cams.conf and restarts it if it dies.

# Load shared configuration.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.sh"

CAM="$1"
IP="$2"

if [ -z "$CAM" ] || [ -z "$IP" ]; then
    echo "Usage: $0 <cam-name> <camera-ip>" >&2
    exit 1
fi

# Wait for the network to come up after boot.
sleep 10

# Set the camera frame size once at startup.
curl -s -H "User-Agent: my-agent" "http://$IP/control?var=framesize&val=$FRAMESIZE" >/dev/null

while true; do
    # Build the output path for the current day/hour and make sure it exists.
    out_dir="$BASE_DIR/$CAM/$(date +%a)/$(date +%H)"
    mkdir -p "$out_dir"
    out_file="$out_dir/${CAM}_$(date +%Y%m%d_%H%M%S).mp4"

    # Pull the stream and remux it to MP4 (no re-encode, no audio).
    # $! is the PID of ffmpeg (last command in the pipeline); killing it makes
    # curl exit via SIGPIPE, cleanly ending this segment.
    curl -s "http://$IP:81/stream" | ffmpeg -i - -vcodec copy -an "$out_file" &
    REC_PID=$!

    # Record for DURATION seconds, then stop this segment.
    sleep "$DURATION"
    if kill -0 "$REC_PID" 2>/dev/null; then
        kill "$REC_PID"
    fi
    wait "$REC_PID" 2>/dev/null

    # If the camera is unreachable the pipeline exits instantly, leaving an empty
    # file. Remove it and back off so we don't spin in a tight loop.
    if [ ! -s "$out_file" ]; then
        rm -f "$out_file"
        sleep 10
    fi
done
