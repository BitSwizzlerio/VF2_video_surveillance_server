This is a rather crude project I only mentioned in passing because I’m rather embarrassed by it. But it has since garnered some interest. So, I’m begrudgingly sharing it on Github. It utilizes the [VisionFive2](https://github.com/starfive-tech/VisionFive2) to collect, organize, and maintain video for several live security cameras around my property. It is fed by various ESP32-CAMs running the esp32-cam-webserver via [PlatformIO](https://platformio.org/). I then use various scripts on the latest Debian release for the VisionFive2 on an eMMC to organize and store these video feeds on a separate dedicated NVMe M.2 drive also on the VisionFive2. Those scripts are provided in this repo for others to freely use. Once those videos are secured on the VisionFive2, I simple use SCP via terminal to download any videos I wish to review. It's not pretty, there is obvious room for improvement, but it's reliable, and that's all I needed. Thus, any progress on my end has since stopped.

I use a separate “cam” shell script for each camera assigned with the proper IP maintained by my router. These scripts use [FFMPEG](https://ffmpeg.org/) to encode the stream into something more manageable. You will need to install FFMPEG on your VisionFive2. I don’t recall the steps but I don’t remember it being complicated either. Should be rather easy. A separate “pave” shell script is used to delete any video that is approaching a week old to make room for new video. It also compresses day old video. Like I said, rather crude, but effective for my needs.

To activate the scripts, I use crontab -e and add the following to mount the drive and execute scripts:
```
@reboot sleep 10 && mount /dev/nvme0n1p1 /mnt/nvme
@reboot sleep 20 && /bin/bash /root/cam1.sh
@reboot sleep 20 && /bin/bash /root/cam2.sh # etc.
0 * * * * /root/pave.sh
```
The file structure looks something like this:

```
root@starfive:~# tree -d /mnt/
/mnt/
`-- nvme
    |-- cam1
    |   |-- Fri
    |   |   |-- 00
    |   |   |-- 01
    |   |   |-- 02
    |   |   |-- 03
    |   |   |-- 04
    |   |   |-- 05
    |   |   |-- 06
    |   |   |-- 07
    |   |   |-- 08
    |   |   |-- 09
    |   |   |-- 10
    |   |   |-- 11
    |   |   |-- 12
    |   |   |-- 13
    |   |   |-- 14
```

Like I said, rather crude.

The ESP32-CAMs I’m using aren’t great. They get an average of a few frames a second on the higher resolutions. But, I don’t see why this wouldn’t work with any feed from any camera. 