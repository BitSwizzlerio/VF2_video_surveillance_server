#!/bin/bash

# Get current day of the week
DAY=$(date +%a)
YESTERDAY=$(date +%a -d "yesterday")

# Get the current hour in 24-hour format
CURRENT_HOUR=$(date +%H)

# get the next hour
NEXT_HOUR=$(date -d '+1 hour' +%H)

# If next hour is 24, reset to 00
if [ $NEXT_HOUR -eq 00 ]; then
  DAY=$(date +%a -d "tomorrow")
fi

# Define directory paths
CAM1_DIR="/mnt/nvme/cam1/$DAY/$NEXT_HOUR"
CAM2_DIR="/mnt/nvme/cam2/$DAY/$NEXT_HOUR"

# Check if the directories exist
if [ ! -d "$CAM1_DIR" ] || [ ! -d "$CAM2_DIR" ]; then
  echo "Error: The directories do not exist. Exiting script."
  exit 1
fi

# Delete the contents of the directories
if ! rm -f "$CAM1_DIR"/* || ! rm -f "$CAM2_DIR"/*; then
  echo "Error: Failed to delete the contents of the directories. Exiting script."
  exit 1
fi

echo "The contents of the directories have been deleted successfully."

# zip current hour of yesterday - saves 100MB+ an hour
tar -czvf /mnt/nvme/cam1/"$YESTERDAY"/"$CURRENT_HOUR"/cam1_"$YESTERDAY"_"$CURRENT_HOUR".tar.gz -C /mnt/nvme/cam1/"$YESTERDAY"/"$CURRENT_HOUR"/ --exclude='*.gz' . 
rm -f /mnt/nvme/cam1/"$YESTERDAY"/"$CURRENT_HOUR"/*.mp4

tar -czvf /mnt/nvme/cam2/"$YESTERDAY"/"$CURRENT_HOUR"/cam2_"$YESTERDAY"_"$CURRENT_HOUR".tar.gz -C /mnt/nvme/cam2/"$YESTERDAY"/"$CURRENT_HOUR"/ --exclude='*.gz' . 
rm -f /mnt/nvme/cam2/"$YESTERDAY"/"$CURRENT_HOUR"/*.mp4





echo "The contents of previous day have been zipped successfully."