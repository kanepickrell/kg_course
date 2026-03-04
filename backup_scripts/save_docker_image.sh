#!/bin/bash

set -e

if [ $# -ne 3 ]; then
    echo "Usage: $0 <container_id_or_name> <new_image_name_and_tag> <output_tar_file>"
    exit 1
fi

CONTAINER_ID="$1"
NEW_IMAGE_NAME="$2"
OUTPUT_FILE="$3"

echo "Committing..."
sudo docker commit "$CONTAINER_ID" "$NEW_IMAGE_NAME"

echo "Docker Saving..."
sudo docker save -o "$OUTPUT_FILE" "$NEW_IMAGE_NAME"

echo "Compressing..."
xz -e9 "$OUTPUT_FILE"

echo "Splitting"
split -b 95M "$OUTPUT_FILE".xz "$OUTPUT_FILE".xz.part-
