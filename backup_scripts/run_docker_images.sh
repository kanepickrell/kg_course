#!/bin/bash
set -e

if [ $# -ne 3 ]; then
    echo "Usage: $0 <tar_file_name> <image_name_and_tag> <new_container_name"
    exit 1
fi

TAR_BASE_NAME="$1"
IMAGE_NAME="$2"
CONTAINER_NAME="$3"

echo "Combining parts..."
cat "$TAR_BASE_NAME".xz.part-* > "$TAR_BASE_NAME".xz

echo "Unzipping whole..."
unxz "$TAR_BASE_NAME".xz

echo "Loading docker image..."
sudo docker load -i "$TAR_BASE_NAME"

echo "Starting docker image..."
sudo docker run --platform linux/arm64/v8 -p 8529:8529 -e ARANGO_ROOT_PASSWORD=devpass --name "$CONTAINER_NAME" "$IMAGE_NAME"