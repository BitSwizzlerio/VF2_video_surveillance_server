#!/bin/bash
# Restarts any camera recorder that has died. Reads the camera list from
# cams.conf and is meant to run from crontab once a minute (and at boot).

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.sh"

while read -r cam ip; do
    if ! pgrep -f "cam.sh $cam\b" > /dev/null; then
        echo "$(date) - recorder for $cam is dead. Restarting..." >> "$WATCHDOG_LOG"
        /bin/bash "$SCRIPT_DIR/cam.sh" "$cam" "$ip" &
    fi
done < <(list_cams)