# VF2 Video Surveillance Server

Scripts that turn a [VisionFive 2](https://github.com/starfive-tech/VisionFive2)
(running the latest Debian release from eMMC) into a small DVR for several live
security cameras. Footage is recorded to a dedicated NVMe M.2 drive, organized
by camera / day / hour, compressed after a few hours, and automatically deleted
once it ages out.

The cameras are [ESP32-CAMs](https://github.com/easytarget/esp32-cam-webserver)
running `esp32-cam-webserver` via [PlatformIO](https://platformio.org/), but any
MJPEG stream should work. Recording is done with [FFmpeg](https://ffmpeg.org/),
so install that on the VisionFive 2 first.

> Based on the original crude-but-reliable setup, refactored so the camera IPs
> live in a config file instead of being hard-coded into several near-identical
> scripts.

## What changed in this version

- **IPs are separated from the code.** All cameras are defined in
  [`cams.conf`](cams.conf); the scripts read that file instead of having IPs
  baked in.
- **One recorder instead of four.** The four duplicated `cam1.sh`–`cam4.sh`
  files are replaced by a single parameterized [`cam.sh`](cam.sh).
- **Central settings** in [`config.sh`](config.sh) (storage path, segment
  length, frame size, retention).
- **Shorter retention.** Compressed footage is deleted after **2 days**
  (`RETENTION_DAYS` in `config.sh`) rather than ~a week. Change one value to
  adjust it.
- **Safer compression.** `pave.sh` now only deletes the source `.mp4` files
  **after** the `tar` archive is created successfully (no more silent data loss
  if `tar` fails).
- **Self-healing folders.** `cam.sh` creates its day/hour folder on the fly, and
  backs off instead of spinning if a camera is offline.
- **Dead code removed** (the unused `USER_AGENT` export, the redundant `cd`, the
  misleading `CURL_PID`).
- Added `crontab.example`, `.gitignore`, and a `LICENSE`.

## Files

| File                | Purpose                                                            |
| ------------------- | ----------------------------------------------------------------- |
| `config.sh`         | Central settings, sourced by every other script.                  |
| `cams.conf.example` | Template for the camera name → IP list. Copy it to `cams.conf`.   |
| `cams.conf`         | Your local camera list (one per line). Git-ignored, not committed.|
| `cam.sh`            | Records one camera's stream. Launched per-camera by the watchdog. |
| `watchdog.sh`       | Starts/keeps a recorder alive for every camera in `cams.conf`.    |
| `pave.sh`           | Hourly: compress footage > 3h old, clear the upcoming hour.       |
| `cleanup.sh`        | Daily: delete `.tar.gz` archives older than `RETENTION_DAYS`.     |
| `gen.sh`            | Pre-create the cam/day/hour folder tree.                          |
| `crontab.example`   | Ready-to-paste cron schedule.                                     |
| `api.py`            | Optional read-only HTTP API for browsing/streaming footage.       |
| `vf2-api.service.example` | systemd unit to run `api.py` on boot.                       |

## Setup

1. **Install FFmpeg and curl** on the VisionFive 2:

   ```bash
   sudo apt update && sudo apt install -y ffmpeg curl
   ```

2. **Get the scripts** into `/root` (keep them together — they source each
   other):

   ```bash
   cd /root
   for f in config.sh cams.conf.example cam.sh watchdog.sh pave.sh cleanup.sh gen.sh; do
     wget "https://raw.githubusercontent.com/BitSwizzlerio/VF2_video_surveillance_server/main/$f"
   done
   chmod +x cam.sh watchdog.sh pave.sh cleanup.sh gen.sh
   ```

3. **Create your `cams.conf`** by copying the example and editing it with your
   cameras' names and IPs (`cams.conf` is git-ignored, so your IPs stay local):

   ```bash
   cp cams.conf.example cams.conf
   nano cams.conf
   ```

   One `name ip` pair per line:

   ```text
   cam1 192.168.0.101
   cam2 192.168.0.102
   cam3 192.168.0.103
   cam4 192.168.0.104
   ```

   (Reserve static leases for these IPs on your router.)

4. **Review `config.sh`** — storage path, segment length, frame size, and how
   many days to keep footage (`RETENTION_DAYS=2`).

5. **Mount the NVMe and create the folders:**

   ```bash
   mkdir -p /mnt/nvme
   mount /dev/nvme0n1p1 /mnt/nvme
   /bin/bash /root/gen.sh
   ```

6. **Schedule everything** with `crontab -e` — see
   [`crontab.example`](crontab.example):

   ```cron
   @reboot sleep 10 && mount /dev/nvme0n1p1 /mnt/nvme
   @reboot sleep 15 && /bin/bash /root/gen.sh
   @reboot sleep 20 && /bin/bash /root/watchdog.sh
   * * * * * /bin/bash /root/watchdog.sh
   0 * * * * /bin/bash /root/pave.sh
   30 3 * * * /bin/bash /root/cleanup.sh
   ```

   The watchdog both starts the recorders at boot and restarts any that die.

## How it works

- **`cam.sh <name> <ip>`** sets the camera frame size, then loops: it records a
  `DURATION`-second MP4 segment into `/mnt/nvme/<name>/<Day>/<Hour>/`, stops,
  and starts the next one. Offline cameras are detected (empty output) and the
  loop backs off instead of busy-looping.
- **`watchdog.sh`** reads `cams.conf` and makes sure exactly one `cam.sh` is
  running per camera, relaunching any that have stopped.
- **`pave.sh`** runs hourly: it compresses each hour folder whose MP4s are more
  than 3 hours old into a `.tar.gz`, deletes the originals only on a successful
  archive, and clears the upcoming hour's folder.
- **`cleanup.sh`** runs daily and removes `.tar.gz` archives older than
  `RETENTION_DAYS` (default **2**).

## Storage layout

```text
/mnt/nvme
└── cam1
    ├── Fri
    │   ├── 00
    │   ├── 01
    │   └── ...
    ├── Mon
    └── ...
```

Each hour folder holds the raw `.mp4` segments until `pave.sh` rolls them into a
single `cam1_<Day>_<Hour>.tar.gz`, which `cleanup.sh` later deletes.

## Reviewing footage

Pull files off the device with `scp`, e.g.:

```bash
scp root@<visionfive-ip>:/mnt/nvme/cam1/Fri/13/cam1_Fri_13.tar.gz .
```

## HTTP API (optional)

[`api.py`](api.py) is a small **read-only** HTTP service (Python 3 standard
library only — no extra packages) that lets a client browse and stream footage
over the LAN instead of using `scp`. It reads `cams.conf` and `config.sh`, scans
the storage tree, and transparently extracts segments from the per-hour
`.tar.gz` archives on demand, so callers always receive plain `.mp4` bytes.

### Deploying the API

1. **Get the files onto the VF2.** `api.py` and `vf2-api.service.example` must
   sit in the **same directory as `config.sh` and `cams.conf`** (the script
   reads both from next to itself). Fetch them like the other scripts:

   ```bash
   cd /root
   wget https://raw.githubusercontent.com/BitSwizzlerio/VF2_video_surveillance_server/main/api.py
   wget https://raw.githubusercontent.com/BitSwizzlerio/VF2_video_surveillance_server/main/vf2-api.service.example
   ```

   (Or copy them from another machine: `scp api.py vf2-api.service.example root@<vf2-ip>:/root/`.)

2. **Confirm Python 3 is present** (stock Debian has it; no `pip` needed):

   ```bash
   python3 --version
   ```

3. **Test run in the foreground:**

   ```bash
   python3 /root/api.py        # serves on 0.0.0.0:8080 by default
   ```

   You should see:

   ```text
   VF2 API serving /mnt/nvme on http://0.0.0.0:8080  (cameras: /root/cams.conf, token: off)
   ```

   From another session (or your client machine), verify:

   ```bash
   curl http://<vf2-ip>:8080/api/health
   curl http://<vf2-ip>:8080/api/cameras
   curl "http://<vf2-ip>:8080/api/cameras/cam1/segments?day=$(date +%F)"
   ```

   Press `Ctrl+C` to stop the test.

4. **Index existing footage (one-time).** Listing archived segments needs a tiny
   `<archive>.idx` sidecar next to each `.tar.gz`; without it the API would have
   to decompress whole archives just to read filenames, which is far too slow on
   the VF2. New archives get an `.idx` automatically (see `pave.sh`); backfill
   the existing ones once:

   ```bash
   python3 /root/api.py --reindex
   ```

5. **Install as a service** so it starts on boot and restarts on failure:

   ```bash
   sudo cp /root/vf2-api.service.example /etc/systemd/system/vf2-api.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now vf2-api
   ```

   Check it with `systemctl status vf2-api` and `journalctl -u vf2-api -f`. If
   your scripts don't live in `/root`, edit `WorkingDirectory`/`ExecStart` in
   the unit to match.

6. **Open the port** if you run a firewall, e.g. `sudo ufw allow 8080/tcp`, and
   reserve a static DHCP lease for the VF2 so the client's URL stays valid.

7. **(Optional) Require a token.** For anything beyond a trusted LAN, set
   `VF2_TOKEN` (see below) and restart the service.

### Endpoints

| Method & path | Returns |
| ------------- | ------- |
| `GET /api/health` | `{"status":"ok"}` |
| `GET /api/cameras` | `[{"id","name","ip"}, ...]` |
| `GET /api/cameras/{id}/segments?day=YYYY-MM-DD` | `[{"start","durationSeconds","source","resourceId"}, ...]` |
| `GET /api/segments/{resourceId}/stream` | `video/mp4` (supports HTTP `Range` for seeking) |

`source` is `LOOSE_MP4` for recent footage or `ARCHIVED` for segments still
inside a `.tar.gz`.

### Configuration (environment variables)

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `VF2_BASE_DIR` | from `config.sh` (`/mnt/nvme`) | storage root |
| `VF2_CAMS_CONF` | `cams.conf` beside the script | camera list |
| `VF2_DURATION` | from `config.sh` (`900`) | nominal segment length |
| `VF2_HOST` / `VF2_PORT` | `0.0.0.0` / `8080` | bind address |
| `VF2_CACHE_DIR` | `<tmp>/vf2_api_cache` | archive extraction cache |
| `VF2_TOKEN` | _(unset)_ | if set, require `Authorization: Bearer <token>` |

> The API is **read-only** and intended for a trusted LAN/VPN. If it must be
> reachable more widely, set `VF2_TOKEN` and/or front it with a reverse proxy.

## Notes

- The ESP32-CAMs are modest — only a few FPS at higher resolutions — but the
  pipeline works with any MJPEG source.
- Everything is configurable from `config.sh` and `cams.conf`; you shouldn't
  need to edit the recording/maintenance logic to add cameras or change
  retention.

## License

[MIT](LICENSE).
