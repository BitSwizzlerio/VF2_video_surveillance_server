#!/bin/bash

# Wait for network connection to be established
sleep 10;

# Set working directory to script directory
cd "$(dirname "$0")";

# Set user agent
export USER_AGENT="my-agent";

# Set frame size
curl -H "User-Agent: my-agent" 'http://xxx.xxx.xxx.xxx/control?var=framesize&val=12'; ###insert camera IP in "x"s

# Set duration of recordings
DURATION=900   # fifteen minutes

CAM="cam1"

# Record video
while true;
  do
    curl http://xxx.xxx.xxx.xxx:xx/stream -s | ffmpeg -i - -vcodec copy -acodec none /mnt/nvme/"$CAM"/"$(date +%a)"/"$(date +%H)"/"$CAM"_$(date +%Y%m%d_%H%M%S).mp4 & ### use your camera's IP and port number in place of "x"s
     
    # The following is very slow: less than 2 fps rather than the 12 fps of above. Due to the use of real-time text overlay
    # may try Gstreamer later, or even OpenCV and see if it has better performance
    
    # curl 'http://xxx.xxx.xxx.xxx:xx/stream' -s | ffmpeg -i - -vf "drawtext=fontfile=/mnt/nvme/font/arial.ttf:text='%{localtime}':fontcolor=white@1.0:fontsize=10:x=5:y=5" -acodec none -f mp4 '/mnt/nvme/cam2/'"$(date +%a)"'/'"$(date +%H)"'/recording_'"$(date +%Y%m%d_%H%M%S)"'.mp4' &
    
    
    CURL_PID=$!

  # Wait for recording to finish
    sleep $DURATION
    
  # Check to see if Process is running and if so, kill it
  if pgrep -x "curl" >/dev/null; then
    echo "Stopping the recording..."
    kill $CURL_PID
  fi

done