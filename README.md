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
> live in a config file instead of being hard-coded into four near-identical
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

## Notes

- The ESP32-CAMs are modest — only a few FPS at higher resolutions — but the
  pipeline works with any MJPEG source.
- Everything is configurable from `config.sh` and `cams.conf`; you shouldn't
  need to edit the recording/maintenance logic to add cameras or change
  retention.

## License

[MIT](LICENSE).
